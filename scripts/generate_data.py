"""
generate_data.py
----------------
Synthetic-data generator for Tostado Restaurant Group.

Produces:
    data/stores.json        500 stores across 4 brands
    data/employees.json     corporate employees grouped by department
    data/vendors.json       phone + internet accounts per store (with logins)
    data/departments.json   departments + their head + admin contact
    data/admins.json        per-department admin login (bcrypt-hashed)

Run:
    python scripts/generate_data.py
"""

import json
import random
import string
from pathlib import Path

import bcrypt
from faker import Faker

fake = Faker("en_US")
Faker.seed(42)
random.seed(42)

ROOT     = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Master config
# ---------------------------------------------------------------------------

BRANDS = [
    {"id": "golden_crisp", "name": "Golden Crisp",    "category": "Fried Chicken", "status": "active"},
    {"id": "stone_fire",   "name": "Stone & Fire",    "category": "Pizza",         "status": "active"},
    {"id": "daybreak",     "name": "Daybreak Coffee", "category": "Coffee",        "status": "active"},
    {"id": "garden_crate", "name": "Garden Crate",    "category": "Salads",        "status": "active"},
]

DEPARTMENTS = [
    "IT",
    "Operations",
    "Marketing",
    "Finance",
    "Human Resources",
    "Procurement",
    "Real Estate",
]

TELECOM_VENDORS  = ["AT&T Business", "Verizon Business", "T-Mobile Business", "Spectrum Voice"]
INTERNET_VENDORS = ["Comcast Business", "Spectrum Business", "Frontier Business", "Cox Business"]

TOTAL_STORES        = 500
STORES_PER_DISTRICT = 12
DISTRICTS_PER_VP    = 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_password(length: int = 14) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(random.choices(chars, k=length))


def make_person():
    first = fake.first_name()
    last  = fake.last_name()
    return {
        "first_name": first,
        "last_name":  last,
        "full_name":  f"{first} {last}",
        "email":      f"{first.lower()}.{last.lower()}@tostadogroup.com",
        "phone":      fake.phone_number(),
    }


def make_address():
    return {
        "street":  fake.street_address(),
        "city":    fake.city(),
        "state":   fake.state_abbr(),
        "zipcode": fake.zipcode(),
    }


# ---------------------------------------------------------------------------
# 1. Org tree: VPs -> District Managers -> Store Managers
# ---------------------------------------------------------------------------

def build_org():
    vps_by_brand       = {}
    districts_by_brand = {}

    for brand in BRANDS:
        brand_stores = TOTAL_STORES // len(BRANDS)              # 125 stores per brand
        n_districts  = -(-brand_stores // STORES_PER_DISTRICT)  # ceiling division
        n_vps        = -(-n_districts  // DISTRICTS_PER_VP)

        vps = []
        for i in range(n_vps):
            p = make_person()
            p.update({
                "id":       f"VP-{brand['id']}-{i+1:02d}",
                "title":    f"VP of Operations - {brand['name']}",
                "brand_id": brand["id"],
            })
            vps.append(p)
        vps_by_brand[brand["id"]] = vps

        districts = []
        for i in range(n_districts):
            p = make_person()
            assigned_vp = vps[i // DISTRICTS_PER_VP]
            p.update({
                "id":         f"DM-{brand['id']}-{i+1:03d}",
                "title":      f"District Manager - {brand['name']}",
                "brand_id":   brand["id"],
                "district":   f"{brand['name']} District {i+1}",
                "reports_to": assigned_vp["id"],
            })
            districts.append(p)
        districts_by_brand[brand["id"]] = districts

    return vps_by_brand, districts_by_brand


# ---------------------------------------------------------------------------
# 2. Stores
# ---------------------------------------------------------------------------

def build_stores(vps_by_brand, districts_by_brand):
    stores = []
    counter = {b["id"]: 0 for b in BRANDS}

    for i in range(TOTAL_STORES):
        brand = BRANDS[i % len(BRANDS)]
        counter[brand["id"]] += 1
        local_idx = counter[brand["id"]]

        district = districts_by_brand[brand["id"]][(local_idx - 1) // STORES_PER_DISTRICT]
        vp = next(v for v in vps_by_brand[brand["id"]] if v["id"] == district["reports_to"])

        manager = make_person()
        manager.update({
            "id":    f"SM-{brand['id']}-{local_idx:04d}",
            "title": "Store Manager",
        })

        slug = brand["id"].replace("_", "")
        store = {
            "store_id":   f"{brand['id'].upper()}-{local_idx:04d}",
            "brand_id":   brand["id"],
            "brand_name": brand["name"],
            "category":   brand["category"],
            "status":     "active",
            "address":    make_address(),
            "phone":      fake.phone_number(),
            "email":      f"store{local_idx:04d}@{slug}.tostadogroup.com",
            "opened_on":  fake.date_between(start_date="-15y", end_date="-3m").isoformat(),
            "closed_on":  None,
            "manager":    manager,
            "district_manager": {
                "id":    district["id"],
                "name":  district["full_name"],
                "phone": district["phone"],
                "email": district["email"],
            },
            "vp_operations": {
                "id":    vp["id"],
                "name":  vp["full_name"],
                "phone": vp["phone"],
                "email": vp["email"],
            },
        }
        stores.append(store)

    return stores


# ---------------------------------------------------------------------------
# 3. Vendor accounts (phone + internet) per store
# ---------------------------------------------------------------------------

def build_vendors(stores):
    vendors = []
    for s in stores:
        vendors.append({
            "vendor_account_id": f"PHONE-{s['store_id']}",
            "store_id":          s["store_id"],
            "service":           "Phone",
            "provider":          random.choice(TELECOM_VENDORS),
            "account_number":    fake.bothify("####-####-####"),
            "monthly_cost":      round(random.uniform(80, 220), 2),
            "support_phone":     fake.phone_number(),
            "portal_url":        "https://business-portal.example.com",
            "login": {
                "username": f"tostado.{s['store_id'].lower()}@tostadogroup.com",
                "password": make_password(),
            },
        })
        vendors.append({
            "vendor_account_id": f"NET-{s['store_id']}",
            "store_id":          s["store_id"],
            "service":           "Internet",
            "provider":          random.choice(INTERNET_VENDORS),
            "account_number":    fake.bothify("INET-####-####"),
            "monthly_cost":      round(random.uniform(120, 400), 2),
            "support_phone":     fake.phone_number(),
            "portal_url":        "https://business.example.net/login",
            "login": {
                "username": f"tostado.{s['store_id'].lower()}",
                "password": make_password(),
            },
        })
    return vendors


# ---------------------------------------------------------------------------
# 4. Departments + Employees + Admin logins
# ---------------------------------------------------------------------------

def build_departments_and_employees():
    employees   = []
    departments = []
    admins      = []

    for dept in DEPARTMENTS:
        # Department head
        head = make_person()
        head.update({
            "id":         f"EMP-{dept[:2].upper()}-001",
            "title":      f"Director of {dept}",
            "department": dept,
        })
        employees.append(head)

        # Admin (the person allowed to update data through the chatbot)
        admin_person = make_person()
        admin_id     = f"EMP-{dept[:2].upper()}-002"
        admin_person.update({
            "id":         admin_id,
            "title":      f"{dept} Administrator",
            "department": dept,
        })
        employees.append(admin_person)

        # Plain admin password (printed once at the end so the user has it)
        admin_pwd = make_password()
        admins.append({
            "department":     dept,
            "username":       admin_person["email"],
            "password_plain": admin_pwd,
            "password_hash":  bcrypt.hashpw(admin_pwd.encode(), bcrypt.gensalt()).decode(),
            "employee_id":    admin_id,
        })

        # 6 to 10 regular department members
        team_size = random.randint(6, 10)
        team = []
        for i in range(team_size):
            p = make_person()
            p.update({
                "id":         f"EMP-{dept[:2].upper()}-{i+3:03d}",
                "title":      fake.job(),
                "department": dept,
            })
            employees.append(p)
            team.append(p["id"])

        departments.append({
            "name":        dept,
            "description": f"The {dept} department of Tostado Restaurant Group.",
            "head": {
                "id":    head["id"],
                "name":  head["full_name"],
                "email": head["email"],
                "phone": head["phone"],
            },
            "admin_contact": {
                "id":    admin_person["id"],
                "name":  admin_person["full_name"],
                "email": admin_person["email"],
                "phone": admin_person["phone"],
            },
            "team_member_ids": team,
        })

    return departments, employees, admins


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Building org tree...")
    vps_by_brand, districts_by_brand = build_org()

    print("Generating 500 stores...")
    stores = build_stores(vps_by_brand, districts_by_brand)

    print("Generating vendor accounts (phone + internet)...")
    vendors = build_vendors(stores)

    print("Generating departments, employees, and admin logins...")
    departments, employees, admins = build_departments_and_employees()

    # Flatten VPs and DMs into the employees roster too
    for vps in vps_by_brand.values():
        for vp in vps:
            employees.append({**vp, "department": "Operations"})
    for dms in districts_by_brand.values():
        for dm in dms:
            employees.append({**dm, "department": "Operations"})

    (DATA_DIR / "stores.json").write_text(json.dumps(stores, indent=2))
    (DATA_DIR / "vendors.json").write_text(json.dumps(vendors, indent=2))
    (DATA_DIR / "employees.json").write_text(json.dumps(employees, indent=2))
    (DATA_DIR / "departments.json").write_text(json.dumps(departments, indent=2))
    (DATA_DIR / "admins.json").write_text(json.dumps(admins, indent=2))
    (DATA_DIR / "brands.json").write_text(json.dumps(BRANDS, indent=2))

    print(f"\nDone. Files written to {DATA_DIR}/")
    print(f"  brands       : {len(BRANDS)}")
    print(f"  stores       : {len(stores)}")
    print(f"  vendors      : {len(vendors)}")
    print(f"  employees    : {len(employees)}")
    print(f"  departments  : {len(departments)}")
    print(f"  admins       : {len(admins)}")

    print("\n--- Department admin credentials (save these somewhere safe) ---")
    for a in admins:
        print(f"  {a['department']:18s} -> {a['username']}  /  {a['password_plain']}")


if __name__ == "__main__":
    main()
