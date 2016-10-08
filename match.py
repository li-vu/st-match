import sublime
import sublime_plugin
import functools
import os, shutil
from traceback import print_exc

def __init_variable(v, value):
  glbs = globals()
  if v not in glbs:
     glbs[v] = value ()

def get_storage(wid):
  __init_variable('match_storages', lambda: {})
  if wid not in match_storages:
    match_storages[wid] = MatchStorage()
  return match_storages[wid]

def remove_storage(wid):
  __init_variable('match_storages', lambda: {})
  if wid in match_storages:
    del match_storages[wid]

class MatchHistory:
  hist = []
  index = None

  def insert(self, user_input):
    if not self.hist or user_input != self.last():
      self.hist.append(user_input)
      self.index = None
      if len(self.hist) > 100:
        self.hist = self.hist[-100:]

  def roll(self, backwards=False):
    if self.index is None:
      self.index = -1 if backwards else 0
    else:
      self.index += -1 if backwards else 1

    if self.index == len(self.hist) or self.index < -len(self.hist):
      self.index = -1 if backwards else 0

  def last(self):
      return self.hist[-1] if self.hist else None

  def get(self, index=None):
      if not index:
        index = self.index
      return self.hist[index] if self.hist else None

  def reset_index(self):
      self.index = None
__init_variable('default_syntax_file', lambda: "match/match.sublime-syntax")
__init_variable('match_panel_name', lambda: "match_st3_output")
__init_variable('match_highlight', lambda: "match_highlight")
__init_variable('match_history', lambda: MatchHistory())

class MatchHistoryCommand(sublime_plugin.TextCommand):
  def run(self, edit, backwards=False):
    match_history.roll(backwards)
    suggest = match_history.get()
    if not suggest:
      suggest = ""
    self.view.erase(edit, sublime.Region(0, self.view.size()))
    self.view.insert(edit, 0, suggest)

class MatchHistoryListener(sublime_plugin.EventListener):
  # restore History index
  def on_deactivated(self, view):
    if view.score_selector(0, 'text.match') > 0:
      match_history.reset_index()

class Match:
  def __init__(self, view, regions, max_name = None):
    if not view or not regions:
      raise ValueError("View, regions: %s, %s" % (view, regions))
    self.view = view
    self.regions = regions
    self.key = (view.id(), self.__get_lineno(view, regions[0].begin()))
    self.max_name = max_name

  def __get_lineno(self, view, pos):
    (r, c) = view.rowcol(pos)
    return r

  def __move_sel_to_region(self, view, regions):
    view.sel().clear()
    # view.sel().add_all(regions)
    view.add_regions(match_highlight, regions, "string", "bookmark", sublime.PERSISTENT | sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)
    view.show(regions[0].begin())
    self.__refresh_selection(view)

  def __refresh_selection(self, view):
    # borrowed from https://github.com/SublimeTextIssues/Core/issues/485
    empty_list = []
    bug_reg_key = "selection_bug_demo_workaround_regions_key"
    view.add_regions(bug_reg_key, empty_list,
                          "no_scope", "", sublime.HIDDEN)
    view.erase_regions(bug_reg_key)

  def hide(self):
    view = self.view
    if not view:
      return
    view.erase_regions(match_highlight)
    view.sel().clear()
    view.sel().add_all(self.regions)
    # view.show(self.regions[0].begin())
    
  def __call__(self):
    view = self.view
    if not view:
      return
    self.__move_sel_to_region(view, self.regions)
    if view.window():
      view.window().focus_view(view)

  def __eq__(self, other):
    if isinstance(other, self.__class__):
      self.key == other.key
    else:
      return False

  def merge(self, other):
    if not isinstance(other, self.__class__):
      raise ValueError("Cannot merge with an object that is not of type Match")
    self.regions += other.regions

  def __str__(self):
    if not self.regions:
      return ""
    view = self.view
    if not view:
      return ""
    lineno = self.__get_lineno(view, self.regions[0].begin())
    text = view.substr(view.line(self.regions[0])).strip()
    name = view.name()
    if not name and view.file_name():
      name = os.path.basename(view.file_name())
    if not name:
      name = view.id()
    return self.__format_line(name, lineno+1, text)

  def __format_line(self, name, lineno, text):
    if self.max_name == None:
      return "%s:%d: %s" % (name, lineno, text)
    if self.max_name < 5:
      return "%d: %s" % (lineno, text)
    base, ext = os.path.splitext(name)
    n = len(base)
    if n > self.max_name:
      b = int((self.max_name-3)/2)
      e = self.max_name - b - 3
      prefix = base[:b]
      suffix = base[-e:]
      print(n, b, e, prefix, suffix)
      shortname = "%s...%s%s" % (prefix, suffix, ext)
      return "%s:%d: %s" % (shortname, lineno, text)
    else:
      return "%s:%d: %s" % (name, lineno, text)

class MatchStorage:
  def __init__(self):
    self.clear()

  def clear(self):
    self.storage = {}
    self.keys = []

  def is_empty(self):
    return self.storage == {}

  def add(self, occ):
    if occ.key in self.storage:
      self.storage[occ.key].merge(occ)
    else:
      self.storage[occ.key] = occ
      self.keys += [occ.key]

  def __getitem__(self, index):
    if index >= len(self.keys):
      print("MatchStorage: Index out of range")
      return None
    key = self.keys[index]
    if key in self.storage:
      return self.storage[key]
    else:
      print("MatchStorage: Key does not exist: %s" % (key))
      return None

  def __str__(self):
    occs = [self.storage[k] for k in self.keys if k in self.storage]
    texts = [str(occ) for occ in occs]
    texts = filter(None, texts)
    return "\n".join(texts)

class MatchShowPanel(sublime_plugin.WindowCommand):
  def run(self):
    panel = self.window.find_output_panel(match_panel_name)
    if not panel:
      return
    self.window.run_command('show_panel', { 'panel': 'output.' + match_panel_name , "toggle": True})
    self.window.focus_view(panel)

class MatchToggleSettingsCommand(sublime_plugin.WindowCommand):
  def __init__(self,  *args, **kwargs):
    super(MatchToggleSettingsCommand, self).__init__(*args, **kwargs)
    self.whitelist = ['match_use_regex', 'match_case_sensitive', 'match_search_in_all_open_files', 'match_embedded_syntax']

  def run(self, setting = None, value = None, toggle = None):
    if not (setting in self.whitelist) or (value == None and toggle == None):
      return
    settings = sublime.load_settings('match.sublime-settings')
    if not value and toggle:
      oldval = settings.get(setting, False)
      value = not oldval
      print(oldval, value)
    settings.set(setting, bool(value))
    sublime.save_settings('match.sublime-settings')

class MatchCommand(sublime_plugin.WindowCommand):
  def run(self, prompt = True):
    view = self.window.active_view()
    if view:
      if len(view.sel()) > 0:
        if view.sel()[0].empty():
          rw = view.word(view.sel()[0])
          word = view.substr(rw).strip()
        else:
          word = view.substr(view.sel()[0])
      else:
        rs = view.get_regions(match_highlight)
        if rs:
          word = view.substr(rs[0])
    if not prompt:
      self.on_done(word)
      return
    v = self.window.show_input_panel(
      'Pattern:',
      word,
      self.on_done,
      None, # on_change
      None  # on_cancel
    )
    v.settings().set('match_input_panel', True)

  # The user has specified a pattern to find matchrences of.
  def on_done(self, pattern):
    match_history.insert(pattern)
    self.window.run_command("match_search", {"pattern": pattern})

class MatchDefinitionCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    view = self.view
    if view.sel()[0].empty():
      rw = view.word(view.sel()[0])
      word = view.substr(rw).strip()
    else:
      word = view.substr(view.sel()[0])
    if not word:
        return
    view.window().run_command("match_search", {"pattern": word, "definition": True})

class MatchSearchCommand(sublime_plugin.WindowCommand):
  def __init__(self,  *args, **kwargs):
    super(MatchSearchCommand, self).__init__(*args, **kwargs)
    self.__load_settings()

  def __del__(self, *args, **kwargs):
    window = self.window
    remove_storage(window.id())
    syntax_file = self.embedded_syntax_file_path
    print("Deleting: ", syntax_file)
    if os.path.exists(syntax_file):
      os.unlink(syntax_file)

  def __load_settings(self):
    self.settings = sublime.load_settings('match.sublime-settings')
    self.use_regex = self.settings.get('match_use_regex', False)
    self.case_sensitive = self.settings.get('match_case_sensitive', False)
    self.all_views = self.settings.get('match_search_in_all_open_files', False)
    self.max_file_name = self.settings.get('match_file_name_shortening_threshold', None)
    self.embedded_syntax = self.settings.get('match_embedded_syntax', True)
    self.font_size = self.settings.get('font_size', None)
    self.embedded_syntax_file = "Default/match_{0}.sublime-syntax".format(self.window.id())
    self.embedded_syntax_file_path = os.path.join(sublime.packages_path(), self.embedded_syntax_file)

  def __embedded_syntax_exists(self):
    return os.path.exists(self.embedded_syntax_file_path)

  def __write_syntax(self, view_syntax):
    default_package_path = os.path.join(sublime.packages_path(), "Default")
    if not os.path.exists(default_package_path):
        os.makedirs(default_package_path)
    syntax_file = self.embedded_syntax_file_path
    if os.path.isfile(syntax_file):
        os.unlink(syntax_file)
    if not view_syntax:
        return
    with open(syntax_file, 'w') as f:
      str = """%YAML1.2
---
# See http://www.sublimetext.com/docs/3/syntax.html
name: match
hidden: true
scope: source.match
contexts:
  main:
    - match: '^(([\w\\\\/_\-\d. ]*):)?(\d+): (?=.*)'
      captures:
        2: string.quoted.double.match,
        3: constant.numeric.match
      push: '{0}'
      with_prototype:
        - match: $
          pop: true""".format(view_syntax)
      f.write(str)

  # The user has specified a pattern to find matchrences of.
  def run(self, pattern = None, definition = False):
    if not pattern:
        return
    self.__load_settings()
    views = self.window.views() if self.all_views else [self.window.active_view()]
    if not self.all_views:
      self.max_file_name = 0
    if not views:
      return
    syntax = self.window.active_view().settings().get('syntax') if self.embedded_syntax and not self.all_views else None
    self.__write_syntax(syntax)    

    storage = get_storage(self.window.id())
    storage.clear()
    [self.__search(v, pattern, definition) for v in views]
    text = str(storage)
    panel = self.window.create_output_panel(match_panel_name)
    font_size = self.font_size
    if not font_size or not isinstance(font_size, int):
      font_size = views[0].settings().get('font_size',10)
    panel.settings().set('font_size', font_size)
    self.__append(panel, text)
    rs = panel.find_all(pattern, self.__search_flags(definition))
    panel.add_regions(match_highlight, rs, "string", "", sublime.PERSISTENT | sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)
    panel.sel().clear()
    panel.sel().add(sublime.Region(0,0))
    self.window.run_command('show_panel', { 'panel': 'output.' + match_panel_name , "toggle": True})
    self.window.focus_view(panel)
    if not storage.is_empty():
      occ = storage[0]
      if occ:
        occ ()

  def __search_flags(self, definition = False):
    flags = 0
    if not self.use_regex or definition:
      flags = flags | sublime.LITERAL
    if not self.case_sensitive and not definition:
      flags = flags | sublime.IGNORECASE
    return flags

  def __search(self, view, pattern, definition = False):
    storage = get_storage(self.window.id())
    f = (lambda p: self.__search_definition(view, p)) if definition else (lambda p: view.find_all(p, self.__search_flags()))
    results = f(pattern)
    occs = [Match(view, [r], max_name = self.max_file_name) for r in results]
    dummy = [storage.add(o) for o in occs]

  def __search_definition(self, view, pattern):
    symbols = view.symbols()
    return [r for (r, t) in symbols if pattern == t]

  def __append(self, view, text):
    try:
      global default_syntax_file
      syntax_file = "Packages/{0}".format(self.embedded_syntax_file if self.__embedded_syntax_exists() else default_syntax_file)
      view.set_syntax_file(syntax_file)
    except:
      print("__append:Error: ",print_exc())
    view.set_read_only(False)
    if (int(sublime.version()) > 3000):
        view.run_command("select_all")
        view.run_command("right_delete")
        view.run_command('append', {'characters': text})
    else:
        edit = view.begin_edit()
        view.erase(edit, sublime.Region(0, view.size()))
        view.insert(edit, 0, text)
        view.end_edit(edit)
    view.set_read_only(True)

class MatchNextCommand(sublime_plugin.TextCommand):
  def run(self, *args, **kwargs):
    window = self.view.window()
    panel = window.find_output_panel(match_panel_name)
    if not panel or self.view.id() != panel.id():
      # default behaviors
      system_command = kwargs["command"] if "command" in kwargs else None
      if system_command:
        system_args = dict({"event": kwargs["event"]}.items())
        system_args.update(dict(kwargs["args"].items()))
        self.view.run_command(system_command, system_args)
      return
    # our stuff
    if window.active_panel() != match_panel_name:
      window.run_command('show_panel', { 'panel': 'output.' + match_panel_name })

    caret = panel.sel()[0].begin()
    (r, c) = panel.rowcol(caret)
    if "forward" in kwargs:
      forward = bool(kwargs["forward"])
      (mr, mc) = panel.rowcol(panel.size())
      if forward:
        r = (r + 1) % (mr + 1)
      else:
        r = (r - 1) if r > 0 else mr
      begin_newline = panel.text_point(r, 0)
      newline = panel.line(begin_newline)
      c = newline.size() if c > newline.size() else c
      newcaret = panel.text_point(r, c)
      newreg = sublime.Region(newcaret, newcaret)
      self.__change_viewpoint(panel, newreg)
    storage = get_storage(window.id())
    if not storage:
      return
    occ = storage[r]
    if occ:
      occ ()

  def __change_viewpoint(self, view , region):
    view.sel().clear()
    view.sel().add(region)
    top_offset = view.text_to_layout(region.begin())[1] - view.line_height()
    view.set_viewport_position((0, top_offset), False)

  def want_event(self):
    return True

class MatchHideRegions(sublime_plugin.EventListener):
  def on_deactivated(self, view):
    window = sublime.active_window()
    if window.active_panel() == match_panel_name:
      return
    panel = window.find_output_panel(match_panel_name)
    if not panel or panel.id() != view.id() or not panel.sel():
      return
    caret = panel.sel()[0].begin()
    (r, c) = panel.rowcol(caret)
    
    storage = get_storage(window.id())
    if not storage:
      return
    occ = storage[r]
    if occ:
      occ.hide()

# def plugin_loaded():
#   default_package_path = os.path.join(sublime.packages_path(), "Default")

#   if not os.path.exists(default_package_path):
#       os.makedirs(default_package_path)

#   source_path = os.path.join(sublime.packages_path(), "match", "match.sublime-syntax")
#   destination_path = os.path.join(default_package_path, "match.sublime-syntax")

#   if os.path.isfile(destination_path):
#       os.unlink(destination_path)

#   shutil.copy(source_path, default_package_path)

# def plugin_unloaded():
#   default_package_path = os.path.join(sublime.packages_path(), "Default")
#   destination_path = os.path.join(default_package_path, "match.sublime-syntax")
#   if os.path.exists(default_package_path) and os.path.isfile(destination_path):
#     os.remove(destination_path)


# class MatchCancelCommand(sublime_plugin.TextCommand):
#   def run(self, edit):
#     window = self.view.window()
#     panel = window.find_output_panel(match_panel_name)

#     print(panel, window.active_panel(), match_pattern_loc)
#     global match_pattern_loc
#     if not panel or window.active_panel() != "output.{0}".format(match_panel_name) or not match_pattern_loc:
#       return
#     (v, rs) = match_pattern_loc
#     v.erase_regions(match_highlight)
#     v.sel().clear()
#     v.sel().add_all(rs)
#     v.show(rs[0].begin())
#     window.run_command('show_panel', { 'panel': 'output.' + match_panel_name , "toggle": True})