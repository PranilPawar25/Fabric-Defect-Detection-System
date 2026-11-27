# Database module for fabric defect detection system
from .log_store import DefectLogStore, get_log_store

__all__ = ['DefectLogStore', 'get_log_store']
