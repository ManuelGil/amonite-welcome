gresource_xml = configure_file(
  input: 'amonite-welcome.gresource.xml.in',
  output: 'amonite-welcome.gresource.xml',
  configuration: {'RESOURCE_BASE_PATH': resource_base_path},
)

gnome.compile_resources(meson.project_name(),
  gresource_xml,
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

_page_names = run_command(
  py,
  '-c',
  'import pathlib, sys; root = pathlib.Path(sys.argv[1]); print("\\n".join(p.name for p in sorted(root.glob("pages.*.yaml"))))',
  meson.current_source_dir(),
  check: true,
).stdout().strip().split('\n')

_string_names = run_command(
  py,
  '-c',
  'import pathlib, sys; root = pathlib.Path(sys.argv[1]); print("\\n".join(p.name for p in sorted(root.glob("strings.*.yaml"))))',
  meson.current_source_dir(),
  check: true,
).stdout().strip().split('\n')

_identity_names = run_command(
  py,
  '-c',
  'import pathlib, sys; root = pathlib.Path(sys.argv[1]); print("\\n".join(p.name for p in sorted(root.glob("identity*.yaml"))))',
  meson.current_source_dir(),
  check: true,
).stdout().strip().split('\n')

# Install from the source tree (packaging / meson install).
install_data(_identity_names, install_dir: pkgdatadir)
install_data('providers.yaml', install_dir: pkgdatadir)
install_data(_page_names, install_dir: pkgdatadir)
install_data(_string_names, install_dir: pkgdatadir)

# Mirror data into the build directory next to the GResource so the uninstalled
# launcher can use builddir/data as pkgdatadir without meson install.
fs = import('fs')
foreach name : _identity_names
  fs.copyfile(name)
endforeach
fs.copyfile('providers.yaml')
foreach name : _page_names
  fs.copyfile(name)
endforeach
foreach name : _string_names
  fs.copyfile(name)
endforeach

install_data(
  'amonite-welcome.desktop',
  install_dir: get_option('datadir') / 'applications',
)

# Freedesktop hicolor application icons (PNG). Icon name matches Icon= in the
# desktop entry (desktop_id / meson project name).
install_subdir(
  'icons/hicolor',
  install_dir: get_option('datadir') / 'icons',
)

desktop_file_validate = find_program('desktop-file-validate', required: false)
if desktop_file_validate.found()
  test(
    'validate desktop file',
    desktop_file_validate,
    args: [meson.current_source_dir() / 'amonite-welcome.desktop'],
  )
endif

subdir('autostart')
