frappe.pages['rfid-load-cont-report'].on_page_load = function(wrapper) {
  const page = frappe.ui.make_app_page({parent: wrapper, title: 'Báo cáo RFID Load Cont', single_column: true});
  frappe.require(['/assets/finished_good_pack_rfid_scan/rfid/report.css',
    '/assets/finished_good_pack_rfid_scan/rfid/report.js'], () => window.RfidDeskReport.mount(page));
};
