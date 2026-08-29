project('amonite-welcome',
  version: '2.0.0',
  license: 'GPL-3.0-or-later',
  meson_version: '>= 0.64.0',
)

# Build identity: app id, GResource path. Application branding is in
# data/identity.base.yaml and data/identity.<lang>.yaml; distribution identity
# comes from /etc/os-release.
app_id = 'org.amonite.Welcome'
resource_base_path = '/' + app_id.replace('.', '/')

gnome = import('gnome')
python = import('python')

dependency('gtk4', version: '>= 4.12')
dependency('pygobject-3.0', version: '>= 3.42')

py = python.find_installation('python3', required: true)

_pyyaml = run_command(py, '-c', 'import yaml', check: false)
if _pyyaml.returncode() != 0
  error('PyYAML (python3-yaml) is required at runtime')
endif

pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'amonite_welcome'

subdir('data')
subdir('amonite_welcome')

install_data(
  'LICENSE',
  install_dir: get_option('datadir') / 'doc' / meson.project_name(),
)

# Uninstalled launcher and meson devenv for development without install.
uninstalled_launcher = configure_file(
  input: 'amonite_welcome/amonite-welcome.in',
  output: meson.project_name(),
  configuration: {
    'PYTHON': py.full_path(),
    'pkgdatadir': meson.project_build_root() / 'data',
    'PROJECT_NAME': meson.project_name(),
    'EXTRA_PYTHONPATH': meson.project_build_root(),
  },
)
run_command('chmod', '755', uninstalled_launcher, check: true)

devenv = environment()
devenv.prepend('PATH', meson.project_build_root())
devenv.prepend('PYTHONPATH', meson.project_build_root())
devenv.set('AMONITE_WELCOME_PKGDATADIR', meson.project_build_root() / 'data')
meson.add_devenv(devenv)

gnome.post_install(
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
