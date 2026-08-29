_ui_sources = [
  '__init__.py',
  'a11y.py',
  'activation.py',
  'components.py',
  'navigation.py',
  'page_view.py',
  'window.py',
]

fs = import('fs')
foreach name : _ui_sources
  fs.copyfile(name)
endforeach

install_data(_ui_sources, install_dir: moduledir / 'ui')
