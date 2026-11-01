#!/usr/bin/env python3
"""user_session.py - Gestión de sesión activa para JarvisBot"""
import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class UserSession:
    user_id: str
    confidence: float
    authenticated_at: float
    last_activity: float


class SessionManager:
    def __init__(self, timeout_minutes: int = 30):
        self.timeout_seconds = timeout_minutes * 60
        self._session: Optional[UserSession] = None

    def set_current_user(self, user_id: str, confidence: float = 1.0):
        now = time.time()
        self._session = UserSession(
            user_id=user_id,
            confidence=confidence,
            authenticated_at=now,
            last_activity=now,
        )
        print(f"[SESSION] ✅ Usuario autenticado: {user_id} (confianza: {confidence:.2f})")

    def get_current_user(self) -> Optional[str]:
        if self._session is None:
            return None
        now = time.time()
        if now - self._session.last_activity > self.timeout_seconds:
            print(f"[SESSION] ⏰ Sesión expirada para {self._session.user_id}")
            self._session = None
            return None
        self._session.last_activity = now
        return self._session.user_id

    def get_session_info(self) -> Optional[dict]:
        if self._session is None:
            return None
        now = time.time()
        elapsed = now - self._session.authenticated_at
        remaining = max(0, self.timeout_seconds - (now - self._session.last_activity))
        return {
            'user_id': self._session.user_id,
            'confidence': self._session.confidence,
            'authenticated_at': self._session.authenticated_at,
            'elapsed_seconds': elapsed,
            'remaining_seconds': remaining,
            'is_active': remaining > 0,
        }

    def clear_session(self):
        if self._session:
            print(f"[SESSION] 🚪 Sesión cerrada para {self._session.user_id}")
        self._session = None

    def is_authenticated(self) -> bool:
        return self.get_current_user() is not None

    def touch(self):
        if self._session:
            self._session.last_activity = time.time()

    def time_since_auth(self) -> Optional[float]:
        if self._session is None:
            return None
        return time.time() - self._session.authenticated_at

    def time_until_expiry(self) -> Optional[float]:
        if self._session is None:
            return None
        now = time.time()
        remaining = self.timeout_seconds - (now - self._session.last_activity)
        return max(0, remaining)


if __name__ == '__main__':
    sm = SessionManager(timeout_minutes=1)
    print(f"¿Autenticado? {sm.is_authenticated()}")
    sm.set_current_user("marc", confidence=0.92)
    print(f"¿Autenticado? {sm.is_authenticated()}")
    print(f"Usuario actual: {sm.get_current_user()}")
    info = sm.get_session_info()
    print(f"Info: {info}")
    print(f"Tiempo hasta expirar: {sm.time_until_expiry():.1f}s")
    sm.clear_session()
    print(f"Tras logout, ¿autenticado? {sm.is_authenticated()}")
