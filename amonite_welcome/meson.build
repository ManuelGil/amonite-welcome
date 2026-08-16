# Python sources shipped with the application (excluding generated config.py).
_python_sources = [
  '__init__.py',
  '__main__.py',
  'main.py',
  'window.py',
  'pages.py',
  'actions.py',
  'strings.py',
  'localeutil.py',
  'system_info.py',
  'identity.py',
  'autostart.py',
]

fs = import('fs')

# Mirror sources into the build directory next to generated config.py so the
# package is importable from a single PYTHONPATH entry (Meson cannot merge a
# source tree with a build tree for one Python package).
foreach name : _python_sources
  fs.copyfile(name)
endforeach

# Installed launcher: package lives under pkgdatadir.
configure_file(
  input: 'amonite-welcome.in',
  output: meson.project_name(),
  configuration: {
    'PYTHON': py.full_path(),
    'pkgdatadir': pkgdatadir,
    'PROJECT_NAME': meson.project_name(),
    'EXTRA_PYTHONPATH': '',
  },
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

config_py = configure_file(
  input: 'config.py.in',
  output: 'config.py',
  configuration: {
    'APP_ID': app_id,
    'RESOURCE_BASE_PATH': resource_base_path,
    'PROJECT_NAME': meson.project_name(),
    'VERSION': meson.project_version(),
  },
)

install_data(
  _python_sources,
  install_dir: moduledir,
)
install_data(config_py, install_dir: moduledir)
