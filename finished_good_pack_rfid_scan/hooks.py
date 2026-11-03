from finished_good_pack_rfid_scan.i18n import message

app_name = "finished_good_pack_rfid_scan"
app_title = "Finished Good Pack RFID Scan"
app_publisher = "Onichan"
app_description = message("app.description", lang="en")
app_email = ""
app_license = "Proprietary"

required_apps = ["factory_management"]

add_to_apps_screen = [{
    "name": app_name,
    "title": app_title,
    "route": "/finished-good-pack-rfid-scan",
    "has_permission": "finished_good_pack_rfid_scan.access.can_open",
}]

before_install = "finished_good_pack_rfid_scan.install.before_install"
before_migrate = "finished_good_pack_rfid_scan.install.before_migrate"
after_install = "finished_good_pack_rfid_scan.install.after_migrate"
after_migrate = "finished_good_pack_rfid_scan.install.after_migrate"
update_website_context = ["finished_good_pack_rfid_scan.web_page.update_website_context"]
