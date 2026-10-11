"""Build mock/customers.json from the kit's public test set (13 cases). Run: python3 mock/tools/make_customers.py
Customer ids are c_<case id lower case>, e.g. c_pub-01. Replace or extend with the final test customers."""
import json, pathlib
root = pathlib.Path(__file__).resolve().parents[2]
cases = json.load(open(root / "build-the-builder-v2" / "public-test-set.json"))
out = {}
for case in cases:
    cid = "c_" + case["id"].lower()
    out[cid] = {
        "customer_id": cid, "case": case["id"],
        "variables": {**case["variables"], "customer_id": cid},
        "identity": case["identity"],
        "products": [{"product_id": f"p{i}", **p} for i, p in enumerate(case["products"], 1)],
        "faults": case.get("faults", []),
    }
(root / "mock" / "customers.json").write_text(json.dumps(out, indent=1) + "\n")
(root / "mock" / "cases.json").write_text(json.dumps(cases, indent=1) + "\n")
print(len(out), "customers")
