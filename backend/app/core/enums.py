"""Domain enumerations shared by ORM models, schemas and services.

Every enum derives from :class:`str` so that it serialises transparently to
JSON and can be used directly as a SQLAlchemy enum value.
"""

from __future__ import annotations

from enum import StrEnum


# --------------------------------------------------------------------- RBAC
class RoleName(StrEnum):
    """Access-control roles.

    ``ADMIN``      - platform administrator, unrestricted.
    ``I4C_ANALYST``- central analytics cell, full case/analytic read-write.
    ``STATE_OFFICER``  - state-level, read across own state.
    ``DISTRICT_OFFICER`` - district-level, read/write within own district.
    ``BANK_ANALYST``    - financial institution liaison, read on linked accounts.
    ``AUDITOR``         - read-only across the audit trail, no case mutation.
    """

    ADMIN = "ADMIN"
    I4C_ANALYST = "I4C_ANALYST"
    STATE_OFFICER = "STATE_OFFICER"
    DISTRICT_OFFICER = "DISTRICT_OFFICER"
    BANK_ANALYST = "BANK_ANALYST"
    AUDITOR = "AUDITOR"


class Permission(StrEnum):
    """Fine-grained capabilities granted through roles."""

    CASE_CREATE = "case:create"
    CASE_READ = "case:read"
    CASE_UPDATE = "case:update"
    CASE_DELETE = "case:delete"
    CASE_ASSIGN = "case:assign"

    COMPLAINT_CREATE = "complaint:create"
    COMPLAINT_READ = "complaint:read"

    TRANSACTION_CREATE = "transaction:create"
    TRANSACTION_READ = "transaction:read"

    ENTITY_READ = "entity:read"
    NETWORK_READ = "network:read"
    NETWORK_WRITE = "network:write"

    PREDICTION_READ = "prediction:read"
    PREDICTION_RUN = "prediction:run"

    ATM_READ = "atm:read"

    ALERT_READ = "alert:read"
    ALERT_WRITE = "alert:write"

    INVESTIGATION_READ = "investigation:read"
    INVESTIGATION_WRITE = "investigation:write"

    SIMULATION_RUN = "simulation:run"

    OUTCOME_WRITE = "outcome:write"

    ANALYTICS_READ = "analytics:read"
    MODEL_READ = "model:read"
    MODEL_TRAIN = "model:train"

    SYNTHETIC_GENERATE = "synthetic:generate"
    LLM_EXPLAIN = "llm:explain"

    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"
    USER_MANAGE = "user:manage"


# --------------------------------------------------------------------- cases
class CaseStatus(StrEnum):
    NEW = "NEW"
    UNDER_ANALYSIS = "UNDER_ANALYSIS"
    PREDICTION_ACTIVE = "PREDICTION_ACTIVE"
    ALERTED = "ALERTED"
    INVESTIGATION_ACTIVE = "INVESTIGATION_ACTIVE"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

    @classmethod
    def open_states(cls) -> frozenset[CaseStatus]:
        return frozenset(
            {
                cls.NEW,
                cls.UNDER_ANALYSIS,
                cls.PREDICTION_ACTIVE,
                cls.ALERTED,
                cls.INVESTIGATION_ACTIVE,
            }
        )


class CasePriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FraudType(StrEnum):
    """Cyber / financial fraud categorisation (NCRP-aligned taxonomy)."""

    UPI_FRAUD = "UPI_FRAUD"
    PHISHING = "PHISHING"
    OTP_FRAUD = "OTP_FRAUD"
    SIM_SWAP = "SIM_SWAP"
    ACCOUNT_TAKEOVER = "ACCOUNT_TAKEOVER"
    SOCIAL_ENGINEERING = "SOCIAL_ENGINEERING"
    INVESTMENT_FRAUD = "INVESTMENT_FRAUD"
    TASK_FRAUD = "TASK_FRAUD"
    SEXTORTION = "SEXTORTION"
    LOTTERY_PRIZE_FRAUD = "LOTTERY_PRIZE_FRAUD"
    FAKE_CUSTOMER_SERVICE = "FAKE_CUSTOMER_SERVICE"
    OTHER = "OTHER"


class DataSource(StrEnum):
    """Provenance marker - **always** attached to generated records."""

    SYNTHETIC = "synthetic"
    DEMO = "demo"
    OPERATIONAL = "operational"


# ---------------------------------------------------------------- complaints
class ComplaintStatus(StrEnum):
    RECEIVED = "RECEIVED"
    UNDER_VERIFICATION = "UNDER_VERIFICATION"
    ACCEPTED = "ACCEPTED"
    REFERRED = "REFERRED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


class ComplaintSource(StrEnum):
    PORTAL = "PORTAL"
    HELPLINE = "HELPLINE"
    BANK_REPORT = "BANK_REPORT"
    POLICE_STATION = "POLICE_STATION"
    I4C_REFERRAL = "I4C_REFERRAL"
    API_PARTNER = "API_PARTNER"
    SYNTHETIC = "SYNTHETIC"


# -------------------------------------------------------------- transactions
class TransactionType(StrEnum):
    UPI_P2M = "UPI_P2M"
    UPI_P2A = "UPI_P2A"
    NEFT = "NEFT"
    IMPS = "IMPS"
    RTGS = "RTGS"
    CARD = "CARD"
    NET_BANKING = "NET_BANKING"
    ATM_WITHDRAWAL = "ATM_WITHDRAWAL"
    CASH_DEPOSIT = "CASH_DEPOSIT"
    CHEQUE = "CHEQUE"
    REFUND = "REFUND"
    UNKNOWN = "UNKNOWN"


class TransactionDirection(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class Channel(StrEnum):
    MOBILE_APP = "MOBILE_APP"
    WEB = "WEB"
    ATM = "ATM"
    POS = "POS"
    BRANCH = "BRANCH"
    UPI = "UPI"
    UNKNOWN = "UNKNOWN"


# ------------------------------------------------------------------- entities
class EntityType(StrEnum):
    VICTIM = "VICTIM"
    SUSPECT = "SUSPECT"
    ACCOUNT = "ACCOUNT"
    MULE_ACCOUNT = "MULE_ACCOUNT"
    PHONE = "PHONE"
    UPI = "UPI"
    DEVICE = "DEVICE"
    ATM = "ATM"
    CSP = "CSP"
    LOCATION = "LOCATION"
    COMPLAINT = "COMPLAINT"
    TRANSACTION = "TRANSACTION"
    IP = "IP"
    EMAIL = "EMAIL"
    BANK = "BANK"
    POLICE_STATION = "POLICE_STATION"
    POLICE_STATION_UNKNOWN = "POLICE_STATION_UNKNOWN"
    PERSON = "PERSON"


class RelationshipType(StrEnum):
    """Typed edges of the fraud-network graph.

    Naming convention is deliberately neutral: an edge records a *known
    association* observed in the source data, never an accusation.
    """

    OWNS = "OWNS"
    REGISTERED_WITH = "REGISTERED_WITH"
    USES = "USES"
    FUNDS_TRANSFERRED_TO = "FUNDS_TRANSFERRED_TO"
    FUNDS_TRANSFERRED_FROM = "FUNDS_TRANSFERRED_FROM"
    WITHDREW_AT = "WITHDREW_AT"
    SENT_TO = "SENT_TO"
    RECEIVED_FROM = "RECEIVED_FROM"
    SHARED_DEVICE = "SHARED_DEVICE"
    SHARED_PHONE = "SHARED_PHONE"
    SHARED_UPI = "SHARED_UPI"
    CO_OCCURRED = "CO_OCCURRED"
    COMPLAINTS_ABOUT = "COMPLAINTS_ABOUT"
    REFERRED_BY = "REFERRED_BY"
    NEARBY = "NEARBY"
    OPERATED_BY = "OPERATED_BY"
    PART_OF_CLUSTER = "PART_OF_CLUSTER"


# ----------------------------------------------------------------- locations
class AtmStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class WithdrawalOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    DECLINED = "DECLINED"
    PARTIAL = "PARTIAL"
    REVERSED = "REVERSED"


# --------------------------------------------------------------- predictions
class PredictionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STALE = "STALE"


class PredictionHorizon(StrEnum):
    """How far ahead the predicted cash-out window reaches."""

    H6 = "H6"
    H12 = "H12"
    H24 = "H24"
    H48 = "H48"
    H72 = "H72"


class ModelStatus(StrEnum):
    DRAFT = "DRAFT"
    TRAINING = "TRAINING"
    ACTIVE = "ACTIVE"
    CANDIDATE = "CANDIDATE"
    RETIRED = "RETIRED"
    FAILED = "FAILED"


# -------------------------------------------------------------------- alerts
class AlertType(StrEnum):
    HIGH_RISK_LOCATION = "HIGH_RISK_LOCATION"
    CASHOUT_WINDOW_APPROACHING = "CASHOUT_WINDOW_APPROACHING"
    NEW_NETWORK_CONNECTION = "NEW_NETWORK_CONNECTION"
    SUSPICIOUS_TRANSACTION_BURST = "SUSPICIOUS_TRANSACTION_BURST"
    MODEL_ANOMALY = "MODEL_ANOMALY"
    PREDICTION_UPDATED = "PREDICTION_UPDATED"
    ENTITY_RESOLVED = "ENTITY_RESOLVED"
    HOTSPOT_ESCALATION = "HOTSPOT_ESCALATION"


class AlertSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK: dict[AlertSeverity, int] = {
    AlertSeverity.LOW: 1,
    AlertSeverity.MEDIUM: 2,
    AlertSeverity.HIGH: 3,
    AlertSeverity.CRITICAL: 4,
}


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"
    SUPPRESSED = "SUPPRESSED"


# ------------------------------------------------------------ investigations
class InvestigationEventType(StrEnum):
    COMPLAINT_RECEIVED = "COMPLAINT_RECEIVED"
    TRANSACTION_DETECTED = "TRANSACTION_DETECTED"
    ENTITY_IDENTIFIED = "ENTITY_IDENTIFIED"
    NETWORK_ANALYZED = "NETWORK_ANALYZED"
    PREDICTION_GENERATED = "PREDICTION_GENERATED"
    ALERT_CREATED = "ALERT_CREATED"
    ALERT_ACKNOWLEDGED = "ALERT_ACKNOWLEDGED"
    INTERVENTION_SIMULATED = "INTERVENTION_SIMULATED"
    INTERVENTION_EXECUTED = "INTERVENTION_EXECUTED"
    OUTCOME_RECORDED = "OUTCOME_RECORDED"
    CASE_STATUS_CHANGED = "CASE_STATUS_CHANGED"
    NOTE_ADDED = "NOTE_ADDED"
    ENTITY_LINKED = "ENTITY_LINKED"
    EVIDENCE_ATTACHED = "EVIDENCE_ATTACHED"


class InvestigationStatus(StrEnum):
    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    MONITORING = "MONITORING"
    INTERVENTION = "INTERVENTION"
    CLOSED = "CLOSED"


class InterventionType(StrEnum):
    MONITOR_ATM = "MONITOR_ATM"
    ALERT_BANK = "ALERT_BANK"
    DISPATCH_UNIT = "DISPATCH_UNIT"
    INCREASE_MONITORING = "INCREASE_MONITORING"
    FREEZE_SIMULATION = "FREEZE_SIMULATION"
    NO_INTERVENTION = "NO_INTERVENTION"


class InterventionStatus(StrEnum):
    SIMULATED = "SIMULATED"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


# ------------------------------------------------------------------- outcome
class OutcomeType(StrEnum):
    PREDICTION_CONFIRMED = "PREDICTION_CONFIRMED"
    PREDICTION_PARTIAL = "PREDICTION_PARTIAL"
    PREDICTION_INCORRECT = "PREDICTION_INCORRECT"
    NO_CASHOUT = "NO_CASHOUT"
    UNKNOWN = "UNKNOWN"


# ------------------------------------------------------------------- events
class RealtimeEventType(StrEnum):
    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"
    COMPLAINT_CREATED = "complaint.created"
    TRANSACTION_CREATED = "transaction.created"
    ENTITY_RESOLVED = "entity.resolved"
    NETWORK_UPDATED = "network.updated"
    PREDICTION_CREATED = "prediction.created"
    PREDICTION_UPDATED = "prediction.updated"
    RISK_UPDATED = "risk.updated"
    ALERT_CREATED = "alert.created"
    ALERT_ACKNOWLEDGED = "alert.acknowledged"
    ALERT_RESOLVED = "alert.resolved"
    INVESTIGATION_UPDATED = "investigation.updated"
    SIMULATION_COMPLETED = "simulation.completed"
    OUTCOME_RECORDED = "outcome.recorded"
    MODEL_TRAINED = "model.trained"
    SYNTHETIC_GENERATED = "synthetic.generated"
    INTERVENTION_EXECUTED = "intervention.executed"
    HEARTBEAT = "heartbeat"


# ------------------------------------------------------------------ models
class TrainingStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ModelKind(StrEnum):
    """Component models of the hybrid ensemble."""

    SPATIAL = "SPATIAL"
    TEMPORAL = "TEMPORAL"
    NETWORK = "NETWORK"
    RANKER = "RANKER"


# -------------------------------------------------------------------- audit
class AuditResult(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    DENIED = "DENIED"


class AuditAction(StrEnum):
    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    TOKEN_REFRESH = "TOKEN_REFRESH"
    USER_CREATE = "USER_CREATE"
    USER_UPDATE = "USER_UPDATE"
    USER_DELETE = "USER_DELETE"
    CASE_CREATE = "CASE_CREATE"
    CASE_READ = "CASE_READ"
    CASE_UPDATE = "CASE_UPDATE"
    CASE_DELETE = "CASE_DELETE"
    COMPLAINT_CREATE = "COMPLAINT_CREATE"
    COMPLAINT_READ = "COMPLAINT_READ"
    TRANSACTION_CREATE = "TRANSACTION_CREATE"
    TRANSACTION_READ = "TRANSACTION_READ"
    PREDICTION_RUN = "PREDICTION_RUN"
    PREDICTION_READ = "PREDICTION_READ"
    ALERT_ACKNOWLEDGE = "ALERT_ACKNOWLEDGE"
    ALERT_RESOLVE = "ALERT_RESOLVE"
    ALERT_READ = "ALERT_READ"
    SIMULATION_RUN = "SIMULATION_RUN"
    INTERVENTION_SIMULATE = "INTERVENTION_SIMULATE"
    INTERVENTION_APPROVE = "INTERVENTION_APPROVE"
    INTERVENTION_EXECUTE = "INTERVENTION_EXECUTE"
    INVESTIGATION_EVENT_CREATE = "INVESTIGATION_EVENT_CREATE"
    OUTCOME_RECORD = "OUTCOME_RECORD"
    AUDIT_READ = "AUDIT_READ"
    SYNTHETIC_GENERATE = "SYNTHETIC_GENERATE"
    MODEL_TRAIN = "MODEL_TRAIN"
    MODEL_READ = "MODEL_READ"
    EXPORT = "EXPORT"
    LLM_EXPLAIN = "LLM_EXPLAIN"
    GEOSPATIAL_READ = "GEOSPATIAL_READ"
    ANALYTICS_READ = "ANALYTICS_READ"


__all__ = [
    "AlertSeverity",
    "AlertStatus",
    "AlertType",
    "AtmStatus",
    "AuditAction",
    "AuditResult",
    "CasePriority",
    "CaseStatus",
    "Channel",
    "ComplaintSource",
    "ComplaintStatus",
    "DataSource",
    "FraudType",
    "InterventionStatus",
    "InterventionType",
    "InvestigationEventType",
    "InvestigationStatus",
    "ModelKind",
    "ModelStatus",
    "OutcomeType",
    "Permission",
    "PredictionHorizon",
    "PredictionStatus",
    "RealtimeEventType",
    "RelationshipType",
    "RoleName",
    "TrainingStatus",
    "TransactionDirection",
    "TransactionType",
    "WithdrawalOutcome",
]
