"""Synthetic dataset generation for the prototype demo + model training.

Every row written here is explicitly tagged ``data_source='synthetic'`` or,
where the schema has no provenance column, is documented as synthetic in the
module docstring.  Recipient details are invented names and masked identifiers;
none of these records represent real people, accounts, or transactions.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AtmStatus,
    CasePriority,
    CaseStatus,
    Channel,
    ComplaintSource,
    ComplaintStatus,
    DataSource,
    EntityType,
    FraudType,
    RelationshipType,
    TransactionDirection,
    TransactionType,
    WithdrawalOutcome,
)
from app.core.security import mask, mask_phone
from app.models import (
    AtmLocation,
    Case,
    CashWithdrawal,
    Complaint,
    Entity,
    EntityRelationship,
    Transaction,
)

FIRST_NAMES = [
    "Aarav",
    "Vivaan",
    "Aditya",
    "Vihaan",
    "Arjun",
    "Sai",
    "Ananya",
    "Diya",
    "Ishaan",
    "Kavya",
    "Rohan",
    "Meera",
    "Kabir",
    "Sanya",
    "Yash",
    "Pooja",
    "Rahul",
    "Neha",
    "Amit",
    "Priya",
    "Ramesh",
    "Sunita",
    "Vikram",
    "Lakshmi",
    "Deepak",
    "Kavita",
    "Sanjay",
    "Anita",
    "Nikhil",
    "Swati",
]
LAST_NAMES = [
    "Sharma",
    "Verma",
    "Gupta",
    "Kumar",
    "Singh",
    "Patel",
    "Yadav",
    "Reddy",
    "Iyer",
    "Nair",
    "Mehta",
    "Agarwal",
    "Mishra",
    "Tripathi",
    "Srivastava",
    "Pandey",
    "Tiwari",
    "Das",
    "Bose",
    "Chopra",
]
BANKS = [
    "State Bank of India",
    "HDFC Bank",
    "ICICI Bank",
    "Punjab National Bank",
    "Bank of Baroda",
    "Axis Bank",
    "Kotak Mahindra Bank",
    "Canara Bank",
    "Union Bank of India",
    "Indian Bank",
]
STREETS = [
    "Hazratganj",
    "Gomti Nagar",
    "Aliganj",
    "Indira Nagar",
    "Chowk",
    "Aminabad",
    "Gomtinagar Extn",
    "Jankipuram",
    "Krishna Nagar",
    "Telibagh",
    "Nirala Nagar",
    "Rajajipuram",
    "Alambagh",
    "Mahanagar",
    "Vibhuti Khand",
]
ZONE_TYPES = ["city_centre", "suburb", "commercial", "residential", "transit"]

DEFAULT_CENTER: dict[str, float | str] = {
    "latitude": 26.8467,
    "longitude": 80.9462,
    "state": "Uttar Pradesh",
}


def _unique(prefix: str, token: uuid.UUID, width: int) -> str:
    return f"{prefix}{str(token)[:width]}".upper()


def _masked_account() -> str:
    return mask(str(uuid.uuid4().int)[:14], keep_last=4)


def _synthetic_phone(rand: random.Random) -> str:
    digits = "".join(str(rand.randint(0, 9)) for _ in range(10))
    return mask_phone(digits)


async def generate_dataset(
    session: AsyncSession,
    *,
    number_of_cases: int,
    number_of_transactions: int,
    number_of_accounts: int,
    number_of_atms: int,
    geographic_area: str,
    center_lat: float | None,
    center_lon: float | None,
    time_range_days: int,
    fraud_patterns: str,
    seed: int | None,
) -> dict[str, int]:
    """Create a fully-linked synthetic dataset for the configured area."""
    rand = random.Random(seed)
    now = datetime.now(UTC)
    center_lat_f = float(DEFAULT_CENTER["latitude"] if center_lat is None else center_lat)
    center_lon_f = float(DEFAULT_CENTER["longitude"] if center_lon is None else center_lon)
    state = str(DEFAULT_CENTER["state"])
    patterns = _fraud_patterns(fraud_patterns)

    counts: dict[str, int] = {
        "atms": 0,
        "entities": 0,
        "relationships": 0,
        "cases": 0,
        "complaints": 0,
        "transactions": 0,
        "withdrawals": 0,
    }

    # --------------------------------------------------------------- ATMs
    atm_rows: list[AtmLocation] = []
    for i in range(number_of_atms):
        lat = _jitter(center_lat_f, 0.18, rand)
        lon = _jitter(center_lon_f, 0.18, rand)
        atm = AtmLocation(
            code=f"SYNATM{(i + 1):04d}",
            name=f"ATM {geographic_area} {i + 1}",
            bank_name=rand.choice(BANKS),
            status=rand.choice([AtmStatus.ACTIVE, AtmStatus.ACTIVE, AtmStatus.ACTIVE, AtmStatus.MAINTENANCE]),
            is_csp=rand.random() < 0.15,
            address=f"{rand.choice(STREETS)} Road, {geographic_area}",
            city=geographic_area,
            state=state,
            service_hours=rand.choice(["24x7", "9am-11pm", "8am-8pm"]),
            base_load=round(rand.uniform(0.2, 0.9), 2),
            monthly_withdrawals=rand.randint(50, 2400),
            zone_type=rand.choice(ZONE_TYPES),
            latitude=lat,
            longitude=lon,
        )
        atm_rows.append(atm)
    session.add_all(atm_rows)
    await session.flush()
    counts["atms"] = len(atm_rows)

    # ----------------------------------------------------------- accounts
    entity_rows: list[Entity] = []
    account_pool: list[Entity] = []
    for i in range(number_of_accounts):
        entity = Entity(
            entity_type=EntityType.ACCOUNT,
            external_id=_unique("ACC", uuid.uuid4(), 13),
            label=f"Mule account {i + 1}",
            is_resolved=True,
            data_source=DataSource.SYNTHETIC,
            metadata_json={"synthetic": True, "holder": _fake_name(rand)},
        )
        entity_rows.append(entity)
        account_pool.append(entity)
    session.add_all(entity_rows)
    await session.flush()
    counts["entities"] += len(entity_rows)

    # ------------------------------------------------------------- cases
    relation_rows: list[EntityRelationship] = []
    txn_rows: list[Transaction] = []
    withdrawal_rows: list[CashWithdrawal] = []
    complaint_rows: list[Complaint] = []
    case_rows: list[Case] = []

    txns_per_case = _spread_transactions(number_of_transactions, number_of_cases)

    for case_index in range(number_of_cases):
        fraud_type = rand.choice(patterns)
        amount = round(rand.uniform(5_000, 1_500_000), 2)
        reported_at = now - timedelta(days=rand.randint(1, max(time_range_days, 1)))
        opened_at = reported_at + timedelta(hours=rand.randint(1, 72))
        priority = (
            CasePriority.HIGH
            if amount > 300_000
            else (CasePriority.MEDIUM if amount > 60_000 else CasePriority.LOW)
        )
        is_cashout_case = rand.random() < 0.45
        status = (
            (CaseStatus.UNDER_ANALYSIS if is_cashout_case else CaseStatus.NEW)
            if case_index % 2 == 0
            else (CaseStatus.RESOLVED if is_cashout_case else CaseStatus.CLOSED)
        )
        victim_name = _fake_name(rand)
        case = Case(
            case_number=_unique("CCI", uuid.uuid4(), 8) + f"{case_index:04d}",
            title=f"{fraud_type.value.replace('_', ' ').title()} case - {victim_name.split()[0]}",
            description=_fake_description(rand, fraud_type, amount),
            status=status,
            priority=priority,
            fraud_type=fraud_type,
            amount=amount,
            complaint_source=ComplaintSource.SYNTHETIC,
            reported_at=reported_at,
            opened_at=opened_at,
            victim_name=victim_name,
            victim_masked_phone=_synthetic_phone(rand),
            victim_masked_email=f"victim{case_index}@example.in",
            victim_masked_account=_masked_account(),
            state=state,
            district=geographic_area,
            locality_note=rand.choice(STREETS),
            latitude=_jitter(center_lat_f, 0.05, rand),
            longitude=_jitter(center_lon_f, 0.05, rand),
            current_risk_score=round(rand.uniform(0.15, 0.9), 3),
            data_source=DataSource.SYNTHETIC,
            investigating_officer_name=_fake_name(rand),
        )
        case_rows.append(case)

        complaint = Complaint(
            complaint_number=_unique("CMP", uuid.uuid4(), 8) + f"{case_index:04d}",
            source=ComplaintSource.SYNTHETIC,
            status=rand.choice([ComplaintStatus.RECEIVED, ComplaintStatus.REFERRED]),
            fraud_type=fraud_type,
            amount=amount,
            reported_at=reported_at,
            victim_name=victim_name,
            victim_phone=_synthetic_phone(rand),
            victim_email=f"victim{case_index}@example.in",
            victim_account_masked=_masked_account(),
            victim_address=f"{rand.randint(1, 999)}, {rand.choice(STREETS)}, {geographic_area}, {state}",
            description=_fake_description(rand, fraud_type, amount),
            transaction_ref=_unique("TXR", uuid.uuid4(), 10),
            data_source=DataSource.SYNTHETIC,
            case=case,
        )
        complaint_rows.append(complaint)

        victim_entity = Entity(
            entity_type=EntityType.VICTIM,
            external_id=_unique("VIC", uuid.uuid4(), 14),
            label=victim_name,
            is_resolved=True,
            data_source=DataSource.SYNTHETIC,
            case_id=case.id,
            metadata_json={"synthetic": True},
        )
        phone_entity = Entity(
            entity_type=EntityType.PHONE,
            external_id=_unique("PHN", uuid.uuid4(), 12),
            label=f"Phone {victim_name}",
            is_resolved=True,
            data_source=DataSource.SYNTHETIC,
            case_id=case.id,
            metadata_json={"synthetic": True},
        )
        entity_rows.append(victim_entity)
        entity_rows.append(phone_entity)
        counts["entities"] += 2

        source_account = rand.choice(account_pool)
        relation_rows.append(
            EntityRelationship(
                source_entity_id=victim_entity.id,
                target_entity_id=source_account.id,
                relationship_type=RelationshipType.OWNS,
                weight=1.0,
                confidence=0.95,
                timestamp=reported_at,
                evidence={"kind": "complaint", "synthetic": True},
            )
        )
        relation_rows.append(
            EntityRelationship(
                source_entity_id=phone_entity.id,
                target_entity_id=source_account.id,
                relationship_type=RelationshipType.REGISTERED_WITH,
                weight=1.0,
                confidence=0.9,
                timestamp=reported_at,
                evidence={"kind": "complaint", "synthetic": True},
            )
        )
        counts["relationships"] += 2

        # ------------------------------------------------------ transactions
        mules = rand.sample(account_pool, min(rand.randint(1, 3), len(account_pool)))
        n_txns = txns_per_case[case_index % len(txns_per_case)] if txns_per_case else 0
        txn_time = reported_at
        for txn_index in range(n_txns):
            txn_time = txn_time + timedelta(minutes=rand.randint(5, 60 * 6))
            is_withdrawal = rand.random() < 0.22
            dest_account = rand.choice(mules) if mules else None
            if is_withdrawal:
                atm = rand.choice(atm_rows)
                txn = Transaction(
                    transaction_ref=_unique("TXN", uuid.uuid4(), 10),
                    amount=round(rand.uniform(500, 10_000), 2),
                    direction=TransactionDirection.DEBIT,
                    type=TransactionType.ATM_WITHDRAWAL,
                    channel=Channel.ATM,
                    timestamp=txn_time,
                    source_account_masked=_masked_account(),
                    destination_account_masked=None,
                    merchant=atm.name,
                    data_source=DataSource.SYNTHETIC,
                    atm_id=atm.id,
                    case_id=case.id,
                    complaint_id=complaint.id,
                    source_entity_id=source_account.id,
                    latitude=atm.latitude,
                    longitude=atm.longitude,
                )
                txn_rows.append(txn)
                withdrawal_rows.append(
                    CashWithdrawal(
                        amount=txn.amount,
                        timestamp=txn_time,
                        outcome=WithdrawalOutcome.SUCCESS,
                        is_mule_withdrawal=True,
                        atm_id=atm.id,
                        account_entity_id=source_account.id,
                        data_source=DataSource.SYNTHETIC,
                    )
                )
                counts["withdrawals"] += 1
                relation_rows.append(
                    EntityRelationship(
                        source_entity_id=source_account.id,
                        target_entity_id=(
                            victim_entity.id if atm.zone_type == "city_centre" else phone_entity.id
                        ),
                        relationship_type=RelationshipType.WITHDREW_AT,
                        weight=0.8,
                        confidence=0.85,
                        timestamp=txn_time,
                        evidence={"kind": "withdrawal", "synthetic": True},
                    )
                )
                counts["relationships"] += 1
            else:
                txn = Transaction(
                    transaction_ref=_unique("TXN", uuid.uuid4(), 10),
                    amount=round(rand.uniform(1_000, 120_000), 2),
                    direction=TransactionDirection.DEBIT,
                    type=rand.choice([TransactionType.UPI_P2M, TransactionType.NEFT, TransactionType.IMPS]),
                    channel=rand.choice([Channel.UPI, Channel.MOBILE_APP, Channel.WEB]),
                    timestamp=txn_time,
                    source_account_masked=_masked_account(),
                    destination_account_masked=_masked_account(),
                    merchant=_fake_name(rand) if txn_index % 3 == 0 else None,
                    data_source=DataSource.SYNTHETIC,
                    case_id=case.id,
                    complaint_id=complaint.id,
                    source_entity_id=source_account.id,
                    destination_entity_id=dest_account.id if dest_account else None,
                    latitude=_jitter(center_lat_f, 0.02, rand),
                    longitude=_jitter(center_lon_f, 0.02, rand),
                )
                txn_rows.append(txn)
                if dest_account is not None:
                    relation_rows.append(
                        EntityRelationship(
                            source_entity_id=source_account.id,
                            target_entity_id=dest_account.id,
                            relationship_type=RelationshipType.FUNDS_TRANSFERRED_TO,
                            weight=0.9,
                            confidence=0.9,
                            timestamp=txn_time,
                            evidence={"kind": "transaction", "synthetic": True},
                        )
                    )
                    counts["relationships"] += 1
            counts["transactions"] += 1

    session.add_all(case_rows)
    await session.flush()
    session.add_all([*complaint_rows, *txn_rows, *relation_rows, *withdrawal_rows])
    await session.flush()

    # --------------------------------------------------------- provenance
    counts.update(
        {
            "cases": len(case_rows),
            "complaints": len(complaint_rows),
            "transactions": len(txn_rows),
            "entities": len(entity_rows),
            "relationships": len(relation_rows),
        }
    )
    counts.setdefault("accounts", number_of_accounts)
    return counts


# ------------------------------------------------------------------ helpers


def _jitter(center: float, radius: float, rand: random.Random) -> float:
    return round(center + rand.uniform(-radius, radius), 6)


def _fake_name(rand: random.Random) -> str:
    return f"{rand.choice(FIRST_NAMES)} {rand.choice(LAST_NAMES)}"


def _fake_description(rand: random.Random, fraud_type: FraudType, amount: float) -> str:
    opener = rand.choice(
        [
            "Reported after an unexpected deduction.",
            "Victim reported receiving a fraudulent payment link.",
            "Account activity flagged as atypical by the bank.",
        ]
    )
    return (
        f"Synthetic {fraud_type.value.replace('_', ' ').lower()} record ({opener}) amount Rs {amount:,.0f}."
    )


def _spread_transactions(total: int, cases: int) -> list[int]:
    if cases <= 0:
        return []
    base, rem = divmod(max(total, 0), cases)
    units = [base + 1 if i < rem else base for i in range(cases)]
    return [max(u, 1) for u in units]


def _fraud_patterns(pattern: str) -> list[FraudType]:
    mapping: dict[str, list[FraudType]] = {
        "ALL": list(FraudType),
        "UPI_FRAUD": [FraudType.UPI_FRAUD],
        "PHISHING": [FraudType.PHISHING, FraudType.OTP_FRAUD],
        "ACCOUNT_TAKEOVER": [FraudType.ACCOUNT_TAKEOVER, FraudType.SIM_SWAP],
        "INVESTMENT_FRAUD": [FraudType.INVESTMENT_FRAUD, FraudType.LOTTERY_PRIZE_FRAUD],
    }
    return mapping.get(pattern, list(FraudType))


__all__ = ["DEFAULT_CENTER", "generate_dataset"]
