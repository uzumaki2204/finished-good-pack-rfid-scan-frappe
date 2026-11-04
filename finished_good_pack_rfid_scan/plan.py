"""Pure booking mapping and scan validation, adapted from the .NET resolver."""

import hashlib
import json
import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from finished_good_pack_rfid_scan.errors import RfidError
from finished_good_pack_rfid_scan.i18n import message


def text(value):
    return str(value or "").strip()


def key(value):
    return text(value).upper()


def clean_rfid(value):
    raw = str(value or "")
    cleaned = "".join(char for char in raw if unicodedata.category(char) != "Cc" or char == "\t")
    return cleaned.strip()[:200]


def rfid_key(value):
    return clean_rfid(value).upper()


def stable_uuid(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "\x1f".join(map(text, parts))))


def snapshot_version(payload):
    basis = {k: v for k, v in payload.items() if k not in ("planVersion", "downloadedAtUtc", "expiresAtUtc")}
    return hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _physical_key(row):
    return key(row.get("orderNo")), key(row.get("doNo")), key(row.get("usedPackNum"))


def resolve_booking(company, booking, sources, packs, details_by_pack, market_lookup):
    """Select only SOAP cartons whose physical pack number was retrieved."""
    booking_id = text(booking.get("innerBookingId"))
    if not booking_id:
        raise RfidError("error.plan_invalid")
    normalized_sources = [row for row in sources if not row.get("isVirtual") and not row.get("sourceIsDel") and text(row.get("usedPackNum"))]
    unique_sources = {}
    for row in normalized_sources:
        unique_sources.setdefault(_physical_key(row), row)

    candidate_boxes = {}
    for pack in packs:
        pack_key = stable_uuid(company, "pack", pack.get("innerPackNum"), pack.get("orderNo"), pack.get("doNo"), pack.get("dispPackNum"))
        if pack_key not in candidate_boxes:
            candidate_boxes[pack_key] = (pack, details_by_pack.get(text(pack.get("innerPackNum")), []))

    items = []
    unmapped = []
    claimed_boxes = set()
    for source in sorted(unique_sources.values(), key=lambda row: (_physical_key(row), key(row.get("setCode")))):
        expected = _physical_key(source)
        matches = [
            (box_id, pack, details) for box_id, (pack, details) in candidate_boxes.items()
            if box_id not in claimed_boxes
            and (key(pack.get("orderNo")), key(pack.get("doNo")), key(pack.get("dispPackNum"))) == expected
            and (not key(source.get("sampleCode")) or not key(pack.get("sampleCode"))
                 or key(source.get("sampleCode")) == key(pack.get("sampleCode")))
        ]
        matches.sort(key=lambda row: (key(row[1].get("dispPackNum")), key(row[1].get("innerPackNum"))))
        if not matches:
            unmapped.append({
                "bookingDetailId": stable_uuid(company, booking_id, source.get("innerContainerId"), source.get("usedPackNum")),
                "innerContainerId": text(source.get("innerContainerId")),
                "dispContainerId": text(source.get("dispContainerId")),
                "orderNo": text(source.get("orderNo")),
                "doNo": text(source.get("doNo")),
                "setCode": text(source.get("setCode")),
                "sampleCode": text(source.get("sampleCode")),
                "usedPackNum": text(source.get("usedPackNum")),
                "plannedBoxCount": 1,
                "mappedBoxCount": 0,
                "unmappedBoxCount": 1,
                "reason": "unmapped",
            })
            continue
        box_id, pack, details = matches[0]
        claimed_boxes.add(box_id)
        market_code = text(pack.get("sampleCode"))[:2]
        market = market_lookup(market_code) or {}
        booking_detail_id = stable_uuid(company, "booking-detail", booking_id, source.get("innerContainerId"), source.get("usedPackNum"))
        for detail in details:
            rfid = clean_rfid(detail.get("rfid"))
            if not rfid:
                continue
            detail_id = stable_uuid(company, "pack-detail", pack.get("innerPackNum"), pack.get("orderNo"), pack.get("doNo"), rfid, detail.get("skuCode"), detail.get("colorCode"), detail.get("sizeCode"))
            items.append({
                "bookingDetailId": booking_detail_id,
                "finishedGoodPackDetailId": detail_id,
                "innerContainerId": text(source.get("innerContainerId")),
                "dispContainerId": text(source.get("dispContainerId")),
                "orderNo": text(source.get("orderNo")),
                "doNo": text(source.get("doNo")),
                "setCode": text(detail.get("setCode")) or text(pack.get("setCode")),
                "sampleCode": text(pack.get("sampleCode")),
                "marketCode": market_code,
                "marketName": text(market.get("market_name")) or text(market.get("name_en")),
                "marketId": text(market.get("name")),
                "skuCode": text(detail.get("skuCode")),
                "usedPackNum": text(source.get("usedPackNum")),
                "warehouse": text(pack.get("warehouse")) or text(source.get("warehouse")),
                "shipToPortCode": text(pack.get("shipToPortCode")),
                "shipToPort": text(pack.get("shipToPort")),
                "quantity": int(source.get("quantity") or 0),
                "rfid": rfid,
                "dispPackNum": text(detail.get("dispPackNum")) or text(pack.get("dispPackNum")),
                "itemCode": text(pack.get("itemCode")),
                "colorCode": text(detail.get("colorCode")),
                "colorName": text(detail.get("colorName")),
                "sizeCode": text(detail.get("sizeCode")),
                "sizeName": text(detail.get("sizeName")),
                "qtyPerSet": int(pack.get("qtyPerSet") or 0),
                "isMetalCheck": text(detail.get("isMetalCheck")),
            })

    if not items:
        raise RfidError("error.booking_unmapped", booking_id=booking_id)
    now = datetime.now(timezone.utc)
    summary = defaultdict(lambda: {"boxCount": 0, "dispPackNums": set()})
    for item in items:
        identity = (item["orderNo"], item["itemCode"], item["sampleCode"], item["marketCode"], item["colorCode"], item["sizeCode"])
        summary[identity]["dispPackNums"].add(item["dispPackNum"])
    summary_rows = []
    for identity, stats in sorted(summary.items()):
        order_no, item_code, sample_code, market_code, color_code, size_code = identity
        summary_rows.append({
            "orderNo": order_no, "itemCode": item_code, "sampleCode": sample_code,
            "marketCode": market_code, "colorCode": color_code, "sizeCode": size_code,
            "boxCount": len(stats["dispPackNums"]),
            "mappedBoxCount": len(stats["dispPackNums"]), "unmappedBoxCount": 0,
            "dispPackNums": sorted(stats["dispPackNums"]),
        })
    warnings = []
    planned_header = int(booking.get("conPreShipPackCnt") or 0)
    actual_header = int(booking.get("conActShipPackCnt") or 0)
    if planned_header > 0 and actual_header != planned_header:
        warnings.append(message("warning.carton_mismatch", booking_id=booking_id, actual=actual_header, planned=planned_header))
    if unmapped:
        warnings.append(message("warning.unmapped_boxes", count=len(unmapped)))
    payload = {
        "companyId": company,
        "bookingId": booking_id,
        "displayBookingId": text(booking.get("dispBookingId")) or booking_id,
        "bookingRequestNo": text(booking.get("bookingRequestNo")),
        "downloadedAtUtc": now.isoformat(),
        "expiresAtUtc": (now + timedelta(days=3)).isoformat(),
        "detailCount": len({text(row.get("innerContainerId")) for row in sources if text(row.get("innerContainerId"))}),
        "soapCartonDetailCount": len(normalized_sources),
        "headerPlannedCartonCount": planned_header,
        "headerActualCartonCount": actual_header,
        "cachedItemCount": len(items),
        "plannedBoxCount": len(unique_sources),
        "mappedBoxCount": len(claimed_boxes),
        "unmappedBoxCount": len(unmapped),
        "hasPlanningMismatch": bool(warnings),
        "planningWarnings": warnings,
        "missingContainerIds": [row["innerContainerId"] for row in unmapped],
        "orderNos": sorted({item["orderNo"] for item in items if item["orderNo"]}),
        "summaryRows": summary_rows,
        "unmappedBoxGroups": unmapped,
        "items": sorted(items, key=lambda item: (item["orderNo"], item["dispPackNum"], item["rfid"])),
    }
    payload["planVersion"] = snapshot_version(payload)
    return payload


def validate_scans(scans, bookings):
    """Resolve submitted scans against frozen server-side booking snapshots."""
    lookup = {}
    for booking in bookings:
        for item in booking.get("items", []):
            detail_id = text(item.get("finishedGoodPackDetailId"))
            if detail_id:
                lookup[(key(booking["bookingId"]), detail_id)] = (booking, item)
    if not isinstance(scans, list) or not scans:
        raise RfidError("error.scan_required")
    if len(scans) > 10000:
        raise RfidError("error.invalid_request")
    seen_details = set()
    seen_rfids = set()
    normalized = []
    for scan in scans:
        if not isinstance(scan, dict):
            raise RfidError("error.scan_invalid")
        detail_id = text(scan.get("finishedGoodPackDetailId"))
        source = lookup.get((key(scan.get("bookingId")), detail_id))
        if not source:
            raise RfidError("error.scan_not_in_plan")
        booking, item = source
        rfid = text(scan.get("rfid"))
        normalized_rfid = rfid_key(rfid)
        if not rfid or len(rfid) > 200 or not normalized_rfid or normalized_rfid != rfid_key(item.get("rfid")):
            raise RfidError("error.scan_not_in_plan")
        if (key(booking["bookingId"]), detail_id) in seen_details or normalized_rfid in seen_rfids:
            raise RfidError("error.scan_duplicate")
        try:
            occurred = datetime.fromisoformat(text(scan.get("scannedAtUtc")).replace("Z", "+00:00"))
            if occurred.tzinfo is None or occurred > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError
        except ValueError:
            raise RfidError("error.scan_invalid") from None
        seen_details.add((key(booking["bookingId"]), detail_id))
        seen_rfids.add(normalized_rfid)
        normalized.append({
            **item,
            "bookingId": booking["bookingId"],
            "displayBookingId": booking.get("displayBookingId", booking["bookingId"]),
            "bookingRequestNo": booking.get("bookingRequestNo", ""),
            "rfid": rfid,
            "scannedAtUtc": occurred.astimezone(timezone.utc).isoformat(),
        })
    return normalized


def booking_delta(old, new):
    old_items = {item["finishedGoodPackDetailId"] for item in (old or {}).get("items", [])}
    new_items = {item["finishedGoodPackDetailId"] for item in new.get("items", [])}
    old_boxes = {(item["orderNo"], item.get("doNo"), item["dispPackNum"]) for item in (old or {}).get("items", [])}
    new_boxes = {(item["orderNo"], item.get("doNo"), item["dispPackNum"]) for item in new.get("items", [])}
    added_items = len(new_items - old_items)
    removed_items = len(old_items - new_items)
    added_boxes = len(new_boxes - old_boxes)
    removed_boxes = len(old_boxes - new_boxes)
    added = added_items or added_boxes
    removed = removed_items or removed_boxes
    return {
        "hasChanges": bool(added or removed),
        "deltaStatus": "Mixed" if added and removed else "Expanded" if added else "Reduced" if removed else "Unchanged",
        "addedItemCount": added_items,
        "removedItemCount": removed_items,
        "addedBoxCount": added_boxes,
        "removedBoxCount": removed_boxes,
        "resolvedPlaceholderBoxCount": max(0, int((old or {}).get("unmappedBoxCount") or 0) - int(new.get("unmappedBoxCount") or 0)),
        "hasUnresolvedPlaceholderDelta": bool(new.get("unmappedBoxCount")),
    }
