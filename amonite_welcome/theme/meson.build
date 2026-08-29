_theme_sources = [
  '__init__.py',
  'palette.py',
  'system.py',
  'theme.py',
]

fs = import('fs')
foreach name : _theme_sources
  fs.copyfile(name)
endforeach

install_data(_theme_sources, install_dir: moduledir / 'theme')
