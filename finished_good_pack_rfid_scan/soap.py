"""Read-only SOAP booking source used by the RFID tablet."""

import re
import time
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree as ET

import frappe
import requests

from finished_good_pack_rfid_scan.errors import RfidError
from finished_good_pack_rfid_scan.plan import key, resolve_booking, text, snapshot_version


SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
CONTRACT = "http://tempuri.org/"
INSTANCE = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("s", SOAP)
ET.register_namespace("i", INSTANCE)
_NUMERIC_CHARACTER_REFERENCE = re.compile(r"&#(?:(?P<decimal>\d+)|x(?P<hex>[0-9A-Fa-f]+));")
_XML_DECLARATION = re.compile(r"^\s*<\?xml\s[^?]*\?>")


def _tag(name):
    return "{" + CONTRACT + "}" + name


def _child(parent, name, value=None):
    node = ET.SubElement(parent, _tag(name))
    if value is not None:
        node.text = str(value)
    return node


def _nil(parent, name):
    node = _child(parent, name)
    node.set("{" + INSTANCE + "}nil", "true")
    return node


def _envelope(operation):
    root = ET.Element("{" + SOAP + "}Envelope")
    body = ET.SubElement(root, "{" + SOAP + "}Body")
    action = _child(body, operation)
    return root, action


def _local(name):
    return name.rsplit("}", 1)[-1]


def _first(root, name):
    return next((node for node in root.iter() if _local(node.tag).casefold() == name.casefold()), None)


def _children(root, name):
    return [node for node in root.iter() if _local(node.tag).casefold() == name.casefold()]


def _value(root, *names):
    for name in names:
        node = _first(root, name)
        if node is not None and node.text is not None:
            return node.text.strip()
    return ""


def _number(root, *names):
    try:
        return int(float(_value(root, *names) or 0))
    except ValueError:
        return 0


def _yes(root, *names):
    return _value(root, *names).casefold() in ("true", "1", "yes")


def _is_xml_scalar(value):
    return (
        value in (0x9, 0xA, 0xD)
        or 0x20 <= value <= 0xD7FF
        or 0xE000 <= value <= 0xFFFD
        or 0x10000 <= value <= 0x10FFFF
    )


def _sanitize_xml(raw):
    without_invalid_scalars = "".join(char for char in raw if _is_xml_scalar(ord(char)))

    def remove_invalid_reference(match):
        try:
            scalar = int(match.group("hex"), 16) if match.group("hex") else int(match.group("decimal"))
        except ValueError:
            return match.group(0)
        return match.group(0) if _is_xml_scalar(scalar) else ""

    return _NUMERIC_CHARACTER_REFERENCE.sub(remove_invalid_reference, without_invalid_scalars)


def _soap_call(account, operation, envelope):
    try:
        response = requests.post(
            _service_url(account.service_url),
            data=ET.tostring(envelope, encoding="utf-8", xml_declaration=True),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": CONTRACT + operation},
            timeout=(5, 40),
        )
        response.raise_for_status()
    except requests.RequestException:
        raise RfidError("error.soap_connection", 502) from None
    try:
        xml_text = _sanitize_xml(response.text).lstrip("\ufeff")
        xml_text = _XML_DECLARATION.sub("", xml_text, count=1)
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        frappe.log_error(
            title=message("diagnostic.soap_operation", operation=operation),
            message=(f"{type(error).__name__}: {error}; "
                     f"content_type={response.headers.get('Content-Type', '')}; "
                     f"response_bytes={len(response.content)}"),
        )
        raise RfidError("error.soap_response", 502) from None
    if _first(root, "Fault") is not None:
        raise RfidError("error.soap_result", 502)
    return root


def _service_url(raw):
    parsed = urlparse(raw)
    path = parsed.path.rstrip("/")
    if not path or path.casefold() == "/webservice":
        path = "/WebService.asmx"
    return urlunparse(parsed._replace(path=path))


def _account(company):
    name = frappe.db.get_value("RFID SOAP Account", {"company": company, "enabled": 1}, "name")
    if not name:
        raise RfidError("error.account_missing")
    account = frappe.get_doc("RFID SOAP Account", name)
    password = account.get_password("password", raise_exception=False)
    if not password:
        raise RfidError("error.account_password")
    return account, password


def _login(account, password):
    envelope, action = _envelope("UserLogin")
    user = _child(action, "user")
    _child(user, "IsDel", 0)
    for name in ("CreateTime", "ModifyTime", "DeleteTime", "StartTime", "EndTime"):
        _nil(user, name)
    for name, value in (
        ("SaveType", 0), ("UserId", account.username), ("Password", password),
        ("UserType", 0), ("UserStatus", 0), ("Sex", 0),
        ("LoginIP", account.login_ip or ""), ("LoginDevice", account.login_device or ""),
    ):
        _child(user, name, value)
    _nil(user, "LoginTime")
    _child(user, "CurrentTime", "0001-01-01T00:00:00")
    _child(user, "IsOnline", 0)
    _child(action, "strError")
    response = _soap_call(account, "UserLogin", envelope)
    if not _yes(response, "UserLoginResult"):
        raise RfidError("error.soap_login", 502)
    soap_user = _first(response, "user")
    if soap_user is None:
        raise RfidError("error.soap_response", 502)
    return soap_user


def _page_count(response):
    page = _first(response, "page")
    return max(1, _number(page, "PagesCount") if page is not None else 1)


def _booking_page(account, booking_id, page_number):
    envelope, action = _envelope("QueryBookingDividPage")
    model = _child(action, "model")
    for name, value in (("containerShipStatus", 99), ("isDel", 0), ("IsChange", 0), ("ChangeFlag", "false")):
        _child(model, name, value)
    _child(action, "doNo", booking_id)
    page = _child(action, "page")
    for name, value in (("RecordCounts", 0), ("CurrentPageRecordCounts", 10000),
                        ("CurrentPageShowCounts", 10000), ("CurrentPageNumber", page_number), ("PagesCount", 1)):
        _child(page, name, value)
    _child(action, "strError")
    response = _soap_call(account, "QueryBookingDividPage", envelope)
    if not _yes(response, "QueryBookingDividPageResult"):
        raise RfidError("error.soap_result", 502)
    bookings = [{
        "innerBookingId": _value(row, "innerBookingId"),
        "dispBookingId": _value(row, "dispBookingId"),
        "bookingRequestNo": _value(row, "BookingRequestNo"),
        "conPreShipPackCnt": _number(row, "conPreShipPackCnt"),
        "conActShipPackCnt": _number(row, "conActShipPackCnt"),
        "modifyTime": _value(row, "modifyTime"),
    } for row in _children(response, "BookingModel")]
    return bookings, _page_count(response)


def _booking_details(account, booking_id):
    envelope, action = _envelope("QueryBookingDetail")
    _child(action, "bookingID", booking_id)
    response = _soap_call(account, "QueryBookingDetail", envelope)
    result = _first(response, "QueryBookingDetailResult")
    if result is None:
        raise RfidError("error.soap_result", 502)
    return [{
        "innerContainerId": _value(row, "innerContainerId"),
        "dispContainerId": _value(row, "dispContainerId"),
        "orderNo": _value(row, "orderNo"),
        "doNo": _value(row, "dONo"),
        "setCode": _value(row, "setCode"),
        "sampleCode": _value(row, "sampleCode"),
        "usedPackNum": _value(row, "UsedpackNum", "UsedPackNum"),
        "quantity": _number(row, "quantity"),
        "warehouse": _value(row, "Warehouse"),
        "sourceIsDel": _number(row, "IsDel"),
        "isVirtual": _yes(row, "IsVirtual"),
    } for row in _children(result, "PrePackingModel")]


def _pack_page(account, do_no, sample_code, page_number):
    envelope, action = _envelope("GetPackListByPage")
    model = _child(action, "model")
    for name, value in (("IsDel", 0), ("DONo", do_no), ("SampleCode", sample_code)):
        _child(model, name, value)
    page = _child(action, "page")
    _child(page, "CurrentPageShowCounts", 10000)
    _child(page, "CurrentPageNumber", page_number)
    _child(action, "strError")
    response = _soap_call(account, "GetPackListByPage", envelope)
    if not _yes(response, "GetPackListByPageResult"):
        raise RfidError("error.soap_result", 502)
    packs = [{
        "innerPackNum": _value(row, "InnerPackNum"),
        "dispPackNum": _value(row, "DispPackNum"),
        "orderNo": _value(row, "OrderNo"),
        "doNo": _value(row, "DONo"),
        "setCode": _value(row, "SetCode"),
        "sampleCode": _value(row, "SampleCode"),
        "itemCode": _value(row, "ItemCode"),
        "qtyPerSet": _number(row, "QtyPerSet"),
        "warehouse": _value(row, "Warehouse"),
        "shipToPortCode": _value(row, "ShipToPortCode"),
        "shipToPort": _value(row, "ShipToPort"),
    } for row in _children(response, "PackInfo")]
    return packs, _page_count(response)


def _pack_details(account, soap_user, pack):
    envelope, action = _envelope("GetPackDetailList")
    _child(action, "modelList")
    model = _child(action, "model")
    _child(model, "IsDel", 0)
    for name in ("CreateTime", "ModifyTime", "DeleteTime", "StartTime", "EndTime"):
        _nil(model, name)
    for name, value in (("SaveType", 0), ("InnerPackNum", pack["innerPackNum"]),
                        ("OrderNo", pack["orderNo"]), ("DONo", pack["doNo"]),
                        ("SetCode", pack["setCode"])):
        _child(model, name, value)
    action.append(soap_user)
    _child(action, "strError")
    response = _soap_call(account, "GetPackDetailList", envelope)
    if not _yes(response, "GetPackDetailListResult"):
        raise RfidError("error.soap_result", 502)
    return [{
        "innerPackNum": _value(row, "InnerPackNum"),
        "dispPackNum": _value(row, "DispPackNum"),
        "orderNo": _value(row, "OrderNo"),
        "doNo": _value(row, "DONo"),
        "setCode": _value(row, "SetCode"),
        "rfid": _value(row, "RFID"),
        "skuCode": _value(row, "SKUCode"),
        "colorCode": _value(row, "ColorCode"),
        "colorName": _value(row, "Color"),
        "sizeCode": _value(row, "SizeCode"),
        "sizeName": _value(row, "Size"),
        "isMetalCheck": _value(row, "IsMetalCheck"),
    } for row in _children(response, "PackDetailInfo")]


def _market(code):
    if not code:
        return None
    return frappe.db.get_value("Market", {"code": code, "is_active": 1}, ["name", "name_en"], as_dict=True)


def _booking_sources(company, booking_id):
    """Only SOAP reads and Frappe master lookups; no SQL Server connection."""
    normalized_id = text(booking_id)
    if not normalized_id:
        raise RfidError("error.bookings_required")
    account, password = _account(company)
    bookings = []
    page_number = 1
    while True:
        page, pages_count = _booking_page(account, normalized_id, page_number)
        bookings.extend(page)
        if page_number >= pages_count:
            break
        page_number += 1
        if page_number > 1000:
            raise RfidError("error.soap_response", 502)
    matching = [row for row in bookings if normalized_id.casefold() in {
        key(row.get("innerBookingId")).casefold(),
        key(row.get("dispBookingId")).casefold(),
        key(row.get("bookingRequestNo")).casefold(),
    }]
    if not matching:
        raise RfidError("error.booking_missing", booking_id=normalized_id)
    booking = max(matching, key=lambda row: text(row.get("modifyTime")))
    if int(booking.get("conActShipPackCnt") or 0) <= 0:
        raise RfidError("error.booking_unready", booking_id=normalized_id)
    sources = _booking_details(account, booking["innerBookingId"])
    groups = defaultdict(set)
    for source in sources:
        if source.get("isVirtual") or source.get("sourceIsDel") or not source.get("usedPackNum"):
            continue
        groups[(source["doNo"], source["sampleCode"])].add(
            (key(source["orderNo"]), key(source["doNo"]), key(source["usedPackNum"])))
    packs_by_id = {}
    for (do_no, sample_code), expected in groups.items():
        page_number = 1
        while True:
            page, pages_count = _pack_page(account, do_no, sample_code, page_number)
            for pack in page:
                identity = (key(pack["orderNo"]), key(pack["doNo"]), key(pack["dispPackNum"]))
                if identity in expected and pack["innerPackNum"]:
                    packs_by_id[pack["innerPackNum"]] = pack
            if page_number >= pages_count:
                break
            page_number += 1
            if page_number > 1000:
                raise RfidError("error.soap_response", 502)
    return account, password, booking, sources, packs_by_id


def preload_booking(company, booking_id):
    return refresh_booking(company, booking_id, full=True)[0]


def refresh_booking(company, booking_id, full=False, previous=None):
    """Server-only Redis cache; expiry safely falls back to a complete read."""
    account, password, booking, sources, packs = _booking_sources(company, booking_id)
    cache_key = "rfid:refresh:v1:" + snapshot_version({"company": company, "booking": booking["innerBookingId"]})
    cached = frappe.cache.get_value(cache_key) or {}
    now = time.time()
    was_mismatch = previous and previous.get("headerPlannedCartonCount", 0) > 0 and previous.get("headerPlannedCartonCount") != previous.get("headerActualCartonCount")
    now_matches = booking.get("conPreShipPackCnt", 0) > 0 and booking.get("conPreShipPackCnt") == booking.get("conActShipPackCnt")
    full = bool(full or not cached or now - cached.get("full_at", 0) >= 600 or (was_mismatch and now_matches))
    old_packs = cached.get("packs", {})
    entries, details = {}, {}
    soap_user = None
    calls = 0
    for pack_id, pack in sorted(packs.items()):
        relevant = [row for row in sources if (key(row.get("orderNo")), key(row.get("doNo")), key(row.get("usedPackNum"))) ==
                    (key(pack.get("orderNo")), key(pack.get("doNo")), key(pack.get("dispPackNum")))]
        signature = snapshot_version({"pack": pack, "sources": relevant})
        old = old_packs.get(pack_id, {})
        rows = old.get("details", [])
        expected = max((int(row.get("quantity") or 0) for row in relevant), default=0)
        incomplete = not rows or any(not text(row.get("rfid")) for row in rows) or (expected > 0 and len(rows) < expected)
        if full or signature != old.get("signature") or incomplete:
            if soap_user is None:
                soap_user = _login(account, password)
            rows = _pack_details(account, soap_user, pack)
            calls += 1
        details[pack_id] = rows
        entries[pack_id] = {"signature": signature, "details": rows}
    result = resolve_booking(company, booking, sources, list(packs.values()), details, _market)
    # Cache only after the entire ERP read succeeds. Never expose these source rows to devices.
    frappe.cache.set_value(cache_key, {"packs": entries, "full_at": now if full else cached.get("full_at", 0)}, expires_in_sec=1800)
    return result, {"fullCheck": full, "checkedAtUtc": datetime.now().astimezone().isoformat(), "detailCalls": calls}
