"""Lossless versioned storage for RFID scan snapshots. No ERP access."""
import json
from datetime import datetime, timezone, timedelta

# Append only. Positions are the on-disk layout contract for storage_version=1.
FIELDS = {
    "finishedGoodPackDetailId": "detail_id", "rfid": "rfid", "bookingId": "booking_id",
    "orderNo": "order_no", "doNo": "do_no", "itemCode": "item_code", "dispPackNum": "disp_pack_num",
    "scannedAtUtc": "source_scanned_at", "isMetalCheck": "source_metal_check",
    "scanId": "source_scan_id", "bookingDetailId": "booking_detail_id",
    "skuCode": "sku_code", "sampleCode": "sample_code", "setCode": "set_code",
    "marketCode": "market_code", "marketName": "market_name", "marketId": "market_id",
    "colorCode": "color_code", "colorName": "color_name", "sizeCode": "size_code", "sizeName": "size_name",
    "qtyPerSet": "qty_per_set", "quantity": "source_quantity", "warehouse": "warehouse",
    "shipToPortCode": "ship_to_port_code", "shipToPort": "ship_to_port",
    "innerContainerId": "inner_container_id", "dispContainerId": "disp_container_id",
    "displayBookingId": "display_booking_id", "bookingRequestNo": "booking_request_no",
    "usedPackNum": "used_pack_num",
}
BASE = {"detail_id", "rfid", "booking_id", "order_no", "do_no", "item_code", "disp_pack_num"}
NEW_FIELDS = [v for v in FIELDS.values() if v not in BASE]
READ_FIELDS = list(dict.fromkeys([*FIELDS.values(), "payload", "storage_version", "source_layout"]))


def value(row, key, default=None):
    return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def dump(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def decode_scan(row):
    if value(row, "payload"):
        return json.loads(value(row, "payload"))
    if value(row, "storage_version") != 1:
        raise ValueError("Missing scan snapshot and unsupported storage version")
    layout = value(row, "source_layout", "") or ""
    if len(layout) != len(FIELDS):
        raise ValueError("Invalid source layout")
    result = {}
    for (key, field), kind in zip(FIELDS.items(), layout):
        if kind == "-":
            continue
        raw = value(row, field)
        if kind == "n": result[key] = None
        elif kind == "s": result[key] = "" if raw is None else str(raw)
        elif kind in ("i", "f", "b"):
            result[key] = json.loads(str(raw))
            expected = {"i": int, "f": float, "b": bool}[kind]
            if type(result[key]) is not expected: raise ValueError("Source type mismatch")
        else: raise ValueError("Unknown source type")
    return result


def encode_scan(data, row):
    if not isinstance(data, dict): raise ValueError("Snapshot is not an object")
    unknown = sorted(set(data) - set(FIELDS))
    if unknown: raise ValueError("Unknown keys: " + ", ".join(unknown))
    fields, layout = {}, []
    for key, field in FIELDS.items():
        if key not in data:
            layout.append("-");continue
        raw = data[key]
        kind = {str:"s", int:"i", float:"f", bool:"b", type(None):"n"}.get(type(raw))
        if not kind: raise ValueError("Unsupported type: " + key)
        encoded = raw if kind == "s" else None if kind == "n" else dump(raw)
        if encoded is not None and len(encoded) > (200 if field == "rfid" else 36 if field == "detail_id" else 100 if field in BASE else 255):
            raise ValueError("Value exceeds column length: " + key)
        if field in BASE:
            if raw is not None and str(value(row,field) or "") != str(encoded or ""):
                raise ValueError("Column conflict: " + key)
        else: fields[field] = encoded
        layout.append(kind)
    if "isMetalCheck" in data:
        metal = str(data["isMetalCheck"] or "").strip().upper() in ("1","TRUE","YES","Y","PASS","ĐÃ RÀ KIM")
        if int(bool(value(row,"is_metal_check"))) != int(metal): raise ValueError("Column conflict: isMetalCheck")
    if data.get("scannedAtUtc") and value(row,"scanned_at"):
        def utc(v):
            d = v if isinstance(v,datetime) else datetime.fromisoformat(str(v).replace("Z","+00:00"))
            return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
        source_time, column_time = utc(data["scannedAtUtc"]), utc(value(row,"scanned_at"))
        # Legacy importer wrote Vietnam wall time into the Datetime column and truncated milliseconds.
        # Preserve BOTH values verbatim; never rewrite the historical column during storage maintenance.
        legacy_time = (source_time + timedelta(hours=7)).replace(microsecond=0)
        if source_time != column_time and legacy_time != column_time:
            raise ValueError("Column conflict: scannedAtUtc")
    fields.update(storage_version=1, source_layout="".join(layout))
    restored = decode_scan({**dict(row), **fields, "payload": None})
    if dump(restored) != dump(data): raise ValueError("Round-trip mismatch")
    return fields


def new_scan_fields(data, row):
    try:
        return {**encode_scan(data,row), "payload": None}
    except (ValueError, TypeError, OverflowError) as error:
        # Never truncate or discard future ERP fields: retain the source until supported.
        return {"payload": dump(data), "storage_version": 0, "storage_error": str(error)}


def field_sql(key):
    field = FIELDS[key]
    return f"CASE WHEN storage_version=1 THEN `{field}` ELSE NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.{key}')), 'null') END"
