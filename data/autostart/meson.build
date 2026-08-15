# System-wide first-run autostart (default enabled).
install_data(
  'amonite-welcome.desktop',
  install_dir: get_option('sysconfdir') / 'xdg' / 'autostart',
)

desktop_file_validate = find_program('desktop-file-validate', required: false)
if desktop_file_validate.found()
  test(
    'validate autostart desktop file',
    desktop_file_validate,
    args: [meson.current_source_dir() / 'amonite-welcome.desktop'],
  )
endif
