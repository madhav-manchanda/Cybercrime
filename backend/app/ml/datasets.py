"""Dataset assembly: builds per-case feature bundles from the database.

The same assembly routine feeds both live prediction and offline training, so
the feature distribution seen during training matches inference. All bundle
materialisation is deterministic and reference-time aware (no look-ahead).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import EntityType
from app.ml.features import (
    AnchorPoint,
    CandidateAtm,
    FeatureBundle,
    HistoricalCashout,
    build_feature_matrix,
    feature_columns,
)
from app.ml.graph_features import extract_features
from app.ml.temporal import build_profile
from app.models import (
    AtmLocation,
    CashWithdrawal,
    Entity,
    EntityRelationship,
    Transaction,
)
from app.services.graph_service import graph_service
from app.services.transaction_service import transaction_service
from app.utils.geo import bbox_lat_lon_filter, bounding_box, distance_km


async def build_bundle(
    session: AsyncSession,
    *,
    case: Any,
    reference_time: datetime | None = None,
    max_distance_km: float | None = None,
    exclude_withdrawal_id: uuid.UUID | None = None,
) -> FeatureBundle:
    """Assemble the full feature context for a case."""
    reference = reference_time or datetime.now(UTC)
    max_distance_km = max_distance_km or settings.ml_max_distance_km

    anchors = await _anchor_points(session, case)
    cashouts, withdrawal_times = await _linked_cashouts(
        session, case, max_distance_km, exclude_withdrawal_id=exclude_withdrawal_id
    )

    profile = build_profile(withdrawal_times, reference=reference)

    graph = await graph_service.load(session, case_id=case.id)
    network = extract_features(graph)
    amount_feats = await transaction_service.case_feature_vector(session, case_id=case.id)

    return FeatureBundle(
        case_id=str(case.id),
        anchor_points=anchors,
        historical_cashouts=cashouts,
        temporal_profile=profile,
        network=network,
        case_amount_features=amount_feats,
        reference_time=reference,
        warnings=[]
        if (anchors or cashouts)
        else [
            "No spatial anchors or historical cash-outs are available; "
            "spatial features default to prior values."
        ],
    )


async def candidate_atms(
    session: AsyncSession,
    *,
    case: Any,
    bundle: FeatureBundle,
    limit: int | None = None,
    max_distance_km: float | None = None,
) -> list[CandidateAtm]:
    """Deterministic candidate ATM set near case activity + linked histories."""
    limit = limit or settings.ml_nearest_atms_per_anchor * 3
    max_distance_km = max_distance_km or settings.ml_max_distance_km

    anchors: list[tuple[float, float]] = []
    if case.latitude is not None and case.longitude is not None:
        anchors.append((case.latitude, case.longitude))
    anchors.extend((a.lat, a.lon) for a in bundle.anchor_points if a.kind != "case")

    base_query = select(AtmLocation)
    if anchors:
        min_lat = min(p[0] for p in anchors) - max_distance_km / 111.0
        max_lat = max(p[0] for p in anchors) + max_distance_km / 111.0
        min_lon = min(p[1] for p in anchors) - max_distance_km / (111.0 * 0.8)
        max_lon = max(p[1] for p in anchors) + max_distance_km / (111.0 * 0.8)
        base_query = bbox_lat_lon_filter(
            base_query,
            AtmLocation,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
        )
    rows = (await session.scalars(base_query)).all()
    atms = [r for r in rows if r.latitude is not None and r.longitude is not None]

    pool: dict[str, AtmLocation] = {}
    if not anchors:
        pool = {str(a.id): a for a in atms}
    else:
        for atm in atms:
            lat, lon = _flt(atm.latitude, 0.0), _flt(atm.longitude, 0.0)
            d = min(float(distance_km(lat, lon, la, lo)) for la, lo in anchors)
            if d <= max_distance_km:
                pool[str(atm.id)] = atm

    # union with ATMs that hosted historically linked cash-outs
    linked_ids = {c.atm_id for c in bundle.historical_cashouts if c.atm_id}
    missing = [uuid.UUID(m) for m in linked_ids if m not in pool]
    if missing:
        extras = (await session.scalars(select(AtmLocation).where(AtmLocation.id.in_(missing)))).all()
        for a in extras:
            pool[str(a.id)] = a

    atm_entities = await _atm_link_counts(session, case.id)

    # deterministic ranking: distance to nearest anchor, then id
    distances: dict[str, float] = {}
    for atm in pool.values():
        lat, lon = _flt(atm.latitude, 0.0), _flt(atm.longitude, 0.0)
        if anchors:
            distances[str(atm.id)] = min(float(distance_km(lat, lon, la, lo)) for la, lo in anchors)
        else:
            distances[str(atm.id)] = 0.0

    ordered = sorted(pool.values(), key=lambda a: (distances.get(str(a.id), 1e9), str(a.id)))
    return [_to_candidate(atm, bundle, atm_entities) for atm in ordered[: max(limit, 1)]]


def _flt(value: float | None, default: float = 0.0) -> float:
    """Coerce optional float coordinates (rows are pre-filtered non-None)."""
    return float(value) if value is not None else default


def _to_candidate(
    atm: AtmLocation,
    bundle: FeatureBundle,
    atm_entities: dict[str, int],
) -> CandidateAtm:
    hist = [c for c in bundle.historical_cashouts if c.atm_id == str(atm.id)]
    hour: float | None = None
    hourly_hours = [h.timestamp.hour for h in hist if h.timestamp is not None]
    if hourly_hours:
        hour = float(max(set(hourly_hours), key=hourly_hours.count))
    return CandidateAtm(
        atm_id=str(atm.id),
        code=atm.code,
        name=atm.name,
        latitude=_flt(atm.latitude, 0.0),
        longitude=_flt(atm.longitude, 0.0),
        bank_name=atm.bank_name,
        is_csp=atm.is_csp,
        base_load=atm.base_load,
        monthly_withdrawals=atm.monthly_withdrawals,
        zone_type=atm.zone_type,
        typical_withdrawal_hour=hour,
        historical_withdrawals=hist,
        network_link_count=atm_entities.get(str(atm.id), 0),
    )


async def _anchor_points(session: AsyncSession, case: Any) -> list[AnchorPoint]:
    anchors: list[AnchorPoint] = []
    if case.latitude is not None and case.longitude is not None:
        anchors.append(AnchorPoint(case.latitude, case.longitude, weight=2.0, kind="case"))
    txns = (await session.scalars(select(Transaction).where(Transaction.case_id == case.id))).all()
    seen: set[tuple[float, float]] = set()
    for txn in txns:
        if txn.latitude is None or txn.longitude is None:
            continue
        key = (round(txn.latitude, 4), round(txn.longitude, 4))
        if key in seen:
            continue
        seen.add(key)
        anchors.append(
            AnchorPoint(
                txn.latitude,
                txn.longitude,
                weight=min(1.0 + txn.amount / 100_000.0, 3.0),
                kind="transaction",
            )
        )
    return anchors[:200]


async def _linked_cashouts(
    session: AsyncSession,
    case: Any,
    max_distance_km: float,
    *,
    exclude_withdrawal_id: uuid.UUID | None = None,
) -> tuple[list[HistoricalCashout], list[datetime]]:
    """Cash-outs linked to the case by entity association or proximity.

    ``exclude_withdrawal_id`` drops the ground-truth withdrawal being predicted
    for, preventing look-ahead leakage during training.
    """
    case_entities = (await session.scalars(select(Entity).where(Entity.case_id == case.id))).all()
    entity_ids = [e.id for e in case_entities]
    cashouts: list[CashWithdrawal] = []
    if entity_ids:
        rows = await session.scalars(
            select(CashWithdrawal).where(CashWithdrawal.account_entity_id.in_(entity_ids))
        )
        cashouts.extend(rows.all())

    if case.latitude is not None and case.longitude is not None:
        min_lat, min_lon, max_lat, max_lon = bounding_box(case.latitude, case.longitude, max_distance_km)
        query = (
            select(CashWithdrawal)
            .join(AtmLocation, AtmLocation.id == CashWithdrawal.atm_id)
            .where(
                AtmLocation.latitude.is_not(None),
                AtmLocation.latitude.between(min_lat, max_lat),
                AtmLocation.longitude.between(min_lon, max_lon),
            )
        )
        rows = await session.scalars(query)
        cashouts.extend(rows.all())

    # dedupe by pk
    seen: set[str] = set()
    unique: list[CashWithdrawal] = []
    for w in cashouts:
        key = str(w.id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(w)

    converted: list[HistoricalCashout] = []
    times: list[datetime] = []
    for w in unique:
        if exclude_withdrawal_id and w.id == exclude_withdrawal_id:
            continue
        atm = w.atm
        converted.append(
            HistoricalCashout(
                lat=_flt(atm.latitude, 0.0) if atm else 0.0,
                lon=_flt(atm.longitude, 0.0) if atm else 0.0,
                amount=w.amount,
                timestamp=w.timestamp,
                atm_id=str(w.atm_id) if w.atm_id else None,
            )
        )
        times.append(w.timestamp)
    return converted, times


async def _atm_link_counts(session: AsyncSession, case_id: uuid.UUID) -> dict[str, int]:
    """Count ATM entities directly linked to this case in the graph."""
    rels = await session.scalars(
        select(EntityRelationship)
        .join(Entity, Entity.id == EntityRelationship.target_entity_id)
        .where(
            Entity.case_id == case_id,
            Entity.entity_type == EntityType.ATM.value,
        )
    )
    counts: dict[str, int] = {}
    for rel in rels.all():
        key = str(rel.target_entity_id)
        counts[key] = counts.get(key, 0) + 1
    return counts


# -------------------------------------------------------------------------
# Offline training / evaluation frame builders
# -------------------------------------------------------------------------


async def build_training_frame(
    session: AsyncSession,
    *,
    limit_cases: int = 100,
    seed: int = 42,
) -> pd.DataFrame:
    """Assemble ``(label, features)`` rows from historical ground truth.

    - Positive: a case-linked cash-out at its ATM.
    - Negative: sampled other candidate ATMs for the same case/time.
    Features are computed with a reference time **before** the withdrawal so
    the target itself never leaks into its own features.
    """
    case_ids = await _case_ids_with_cashouts(session, limit_cases)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for case_id in case_ids:
        case = await _get_case(session, case_id)
        if case is None:
            continue
        cashouts = await _case_cashouts(session, case)
        for w in cashouts[:25]:
            if w.atm_id is None:
                continue
            reference = w.timestamp - timedelta(hours=1)
            bundle = await build_bundle(
                session,
                case=case,
                reference_time=reference,
                exclude_withdrawal_id=w.id,
            )
            candidates = await candidate_atms(
                session,
                case=case,
                bundle=bundle,
                limit=settings.ml_nearest_atms_per_anchor * 3,
            )
            feature_df, _ = build_feature_matrix(bundle, candidates)
            feature_df = feature_df.fillna(-999.0).replace([np.inf, -np.inf], -999.0)
            pos_row = feature_df[feature_df["atm_id"] == str(w.atm_id)]
            if pos_row.empty:
                continue
            rows.append(
                {
                    "case_id": str(case_id),
                    "reference": reference.isoformat(),
                    "atm_id": str(w.atm_id),
                    "label": 1,
                    **{c: float(pos_row.iloc[0][c]) for c in feature_columns()},
                }
            )
            neg_ids = [c.atm_id for c in candidates if c.atm_id != str(w.atm_id)]
            rng.shuffle(neg_ids)
            for neg_id in neg_ids[: int(settings.ml_negative_sampling_ratio)]:
                neg_row = feature_df[feature_df["atm_id"] == neg_id]
                if neg_row.empty:
                    continue
                rows.append(
                    {
                        "case_id": str(case_id),
                        "reference": reference.isoformat(),
                        "atm_id": neg_id,
                        "label": 0,
                        **{c: float(neg_row.iloc[0][c]) for c in feature_columns()},
                    }
                )
    return pd.DataFrame(rows)


async def _case_ids_with_cashouts(session: AsyncSession, limit: int) -> list[Any]:
    """Case ids that own at least one entity-linked cash-out."""

    entities = (
        await session.scalars(
            select(Entity).where(
                Entity.case_id.is_not(None),
                Entity.id.in_(
                    select(CashWithdrawal.account_entity_id).where(
                        CashWithdrawal.account_entity_id.is_not(None)
                    )
                ),
            )
        )
    ).all()
    ids: list[Any] = []
    seen: set[Any] = set()
    for ent in entities:
        if ent.case_id and ent.case_id not in seen:
            seen.add(ent.case_id)
            ids.append(ent.case_id)
        if len(ids) >= limit:
            break
    return ids


async def _get_case(session: AsyncSession, case_id: Any) -> Any:
    from app.models import Case

    return await session.get(Case, uuid.UUID(str(case_id)))


async def _case_cashouts(session: AsyncSession, case: Any) -> list[CashWithdrawal]:
    entities = (await session.scalars(select(Entity).where(Entity.case_id == case.id))).all()
    if not entities:
        return []
    entity_ids = [e.id for e in entities]
    return list(
        (
            await session.scalars(
                select(CashWithdrawal).where(CashWithdrawal.account_entity_id.in_(entity_ids))
            )
        ).all()
    )


async def build_eval_frame(session: AsyncSession, *, seed: int = 7) -> pd.DataFrame:
    """Evaluation frame over a smaller recent ground-truth subset."""
    return await build_training_frame(session, limit_cases=50, seed=seed)


__all__ = ["build_bundle", "build_eval_frame", "build_training_frame", "candidate_atms"]
