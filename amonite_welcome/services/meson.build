_service_sources = [
  '__init__.py',
  'autostart.py',
  'capabilities.py',
  'catalog.py',
  'identity.py',
  'locale.py',
  'providers.py',
  'system_info.py',
]

fs = import('fs')
foreach name : _service_sources
  fs.copyfile(name)
endforeach

install_data(_service_sources, install_dir: moduledir / 'services')
