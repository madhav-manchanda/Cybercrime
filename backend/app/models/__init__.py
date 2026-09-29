"""ORM model package - importing it registers every table on ``Base.metadata``."""

from app.models.account import Account, Device, PhoneNumber, UpiId
from app.models.alert import Alert, RiskScore
from app.models.atm import AtmLocation, CashWithdrawal
from app.models.audit import AuditLog
from app.models.case import Case
from app.models.complaint import Complaint
from app.models.entity import Entity, EntityRelationship
from app.models.investigation import Intervention, InvestigationEvent
from app.models.model_run import ModelMetric, ModelRun
from app.models.outcome import Outcome
from app.models.prediction import Prediction, PredictionLocation
from app.models.refresh_token import RefreshTokenSession
from app.models.transaction import Transaction
from app.models.user import Role, User

__all__ = [
    "Account",
    "Alert",
    "AtmLocation",
    "AuditLog",
    "Case",
    "CashWithdrawal",
    "Complaint",
    "Device",
    "Entity",
    "EntityRelationship",
    "Intervention",
    "InvestigationEvent",
    "ModelMetric",
    "ModelRun",
    "Outcome",
    "PhoneNumber",
    "Prediction",
    "PredictionLocation",
    "RefreshTokenSession",
    "RiskScore",
    "Role",
    "Transaction",
    "UpiId",
    "User",
]
