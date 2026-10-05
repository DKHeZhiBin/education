from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.domain.auth import AuthenticatedUser, GuardianLinkResponse
from app.models import (
    AccountActionToken,
    GuardianProfile,
    GuardianStudentLink,
    RefreshSession,
    StudentProfile,
    User,
)


class EmailAlreadyRegistered(Exception):
    pass


class GuardianLinkAlreadyExists(Exception):
    pass


RefreshRotationStatus = Literal["rotated", "invalid", "reused"]


class AuthRepository:
    def __init__(self, engine: Engine, session_factory: sessionmaker[Session]) -> None:
        self.engine = engine
        self.session_factory = session_factory

    def create_user(
        self,
        email: str,
        password_hash: str,
        role: str,
        display_name: str,
        grade_band: str | None,
    ) -> AuthenticatedUser:
        try:
            with self.session_factory.begin() as db:
                if db.scalar(select(User.id).where(User.email == email)) is not None:
                    raise EmailAlreadyRegistered(email)
                user = User(
                    email=email,
                    password_hash=password_hash,
                    role=role,
                    account_status="active",
                    token_version=1,
                    email_verified_at=None,
                )
                db.add(user)
                db.flush()
                if role == "student":
                    db.add(StudentProfile(
                        user_id=user.id,
                        display_name=display_name,
                        grade_band=grade_band or "middle",
                    ))
                else:
                    db.add(GuardianProfile(
                        user_id=user.id,
                        display_name=display_name,
                    ))
                db.flush()
                return self._identity(user, display_name, grade_band)
        except IntegrityError as error:
            raise EmailAlreadyRegistered(email) from error

    def get_user_by_email(self, email: str) -> User | None:
        with self.session_factory() as db:
            return db.scalar(self._user_query().where(User.email == email))

    def get_user_by_id(self, user_id: str) -> User | None:
        with self.session_factory() as db:
            return db.scalar(self._user_query().where(User.id == user_id))

    def mark_login(self, user_id: str) -> None:
        with self.session_factory.begin() as db:
            user = db.get(User, user_id)
            if user is not None:
                user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)

    def create_action_token(
        self,
        user_id: str,
        purpose: str,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        now = self._now()
        with self.session_factory.begin() as db:
            previous = db.scalars(select(AccountActionToken).where(
                AccountActionToken.user_id == user_id,
                AccountActionToken.purpose == purpose,
                AccountActionToken.used_at.is_(None),
            ).with_for_update()).all()
            for token in previous:
                token.used_at = now
            db.add(AccountActionToken(
                user_id=user_id,
                purpose=purpose,
                token_hash=token_hash,
                expires_at=expires_at,
            ))

    def verify_email(self, token_hash: str) -> AuthenticatedUser | None:
        now = self._now()
        with self.session_factory.begin() as db:
            token = db.scalar(select(AccountActionToken).where(
                AccountActionToken.token_hash == token_hash,
                AccountActionToken.purpose == "email_verification",
            ).with_for_update())
            if token is None or token.used_at is not None or token.expires_at <= now:
                return None
            user = db.scalar(self._user_query().where(User.id == token.user_id).with_for_update())
            if user is None or user.account_status != "active":
                return None
            token.used_at = now
            user.email_verified_at = user.email_verified_at or now
            db.flush()
            return self.to_identity(user)

    def reset_password(self, token_hash: str, password_hash: str) -> bool:
        now = self._now()
        with self.session_factory.begin() as db:
            token = db.scalar(select(AccountActionToken).where(
                AccountActionToken.token_hash == token_hash,
                AccountActionToken.purpose == "password_reset",
            ).with_for_update())
            if token is None or token.used_at is not None or token.expires_at <= now:
                return False
            user = db.get(User, token.user_id, with_for_update=True)
            if user is None or user.account_status != "active":
                return False
            token.used_at = now
            user.password_hash = password_hash
            user.token_version += 1
            self._revoke_user_refresh_sessions(db, user.id, now)
            return True

    def change_password(self, user_id: str, password_hash: str) -> bool:
        now = self._now()
        with self.session_factory.begin() as db:
            user = db.get(User, user_id, with_for_update=True)
            if user is None or user.account_status != "active":
                return False
            user.password_hash = password_hash
            user.token_version += 1
            self._revoke_user_refresh_sessions(db, user.id, now)
            return True

    def create_refresh_session(
        self,
        user_id: str,
        family_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        with self.session_factory.begin() as db:
            db.add(RefreshSession(
                user_id=user_id,
                family_id=family_id,
                token_hash=token_hash,
                expires_at=expires_at,
            ))

    def rotate_refresh_session(
        self,
        current_hash: str,
        replacement_hash: str,
        replacement_expires_at: datetime,
    ) -> tuple[RefreshRotationStatus, AuthenticatedUser | None]:
        now = self._now()
        with self.session_factory.begin() as db:
            current = db.scalar(select(RefreshSession).where(
                RefreshSession.token_hash == current_hash,
            ).with_for_update())
            if current is None:
                return "invalid", None
            if current.used_at is not None or current.revoked_at is not None:
                self._revoke_refresh_family(db, current.family_id, now)
                user = db.get(User, current.user_id, with_for_update=True)
                if user is not None:
                    user.token_version += 1
                return "reused", None
            if current.expires_at <= now:
                current.revoked_at = now
                return "invalid", None

            user = db.scalar(self._user_query().where(User.id == current.user_id).with_for_update())
            if (
                user is None
                or user.account_status != "active"
                or user.email_verified_at is None
            ):
                current.revoked_at = now
                return "invalid", None

            replacement = RefreshSession(
                id=str(uuid4()),
                user_id=current.user_id,
                family_id=current.family_id,
                token_hash=replacement_hash,
                expires_at=replacement_expires_at,
            )
            db.add(replacement)
            current.used_at = now
            current.revoked_at = now
            current.replaced_by_id = replacement.id
            db.flush()
            return "rotated", self.to_identity(user)

    def revoke_refresh_family(self, token_hash: str) -> None:
        now = self._now()
        with self.session_factory.begin() as db:
            current = db.scalar(select(RefreshSession).where(
                RefreshSession.token_hash == token_hash,
            ).with_for_update())
            if current is not None:
                self._revoke_refresh_family(db, current.family_id, now)
                user = db.get(User, current.user_id, with_for_update=True)
                if user is not None:
                    user.token_version += 1

    def revoke_tokens(self, user_id: str) -> None:
        with self.session_factory.begin() as db:
            user = db.get(User, user_id)
            if user is not None:
                user.token_version += 1
                self._revoke_user_refresh_sessions(db, user_id, self._now())

    def create_guardian_link(
        self,
        guardian_user_id: str,
        student_email: str,
        relationship: str,
    ) -> GuardianLinkResponse | None:
        with self.session_factory.begin() as db:
            student = db.scalar(
                self._user_query().where(User.email == student_email, User.role == "student")
            )
            if student is None:
                return None
            existing = db.scalar(select(GuardianStudentLink).where(
                GuardianStudentLink.guardian_user_id == guardian_user_id,
                GuardianStudentLink.student_user_id == student.id,
            ))
            if existing is not None and existing.status != "revoked":
                raise GuardianLinkAlreadyExists
            link = existing or GuardianStudentLink(
                guardian_user_id=guardian_user_id,
                student_user_id=student.id,
            )
            link.relationship_type = relationship
            link.status = "pending"
            link.consented_at = None
            if existing is None:
                db.add(link)
            db.flush()
            return self._link_response(db, link)

    def accept_guardian_link(self, link_id: str, student_user_id: str) -> GuardianLinkResponse | None:
        with self.session_factory.begin() as db:
            link = db.scalar(select(GuardianStudentLink).where(
                GuardianStudentLink.id == link_id,
                GuardianStudentLink.student_user_id == student_user_id,
                GuardianStudentLink.status == "pending",
            ))
            if link is None:
                return None
            link.status = "active"
            link.consented_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.flush()
            return self._link_response(db, link)

    def revoke_guardian_link(self, link_id: str, actor_user_id: str) -> bool:
        with self.session_factory.begin() as db:
            link = db.scalar(select(GuardianStudentLink).where(
                GuardianStudentLink.id == link_id,
                (GuardianStudentLink.guardian_user_id == actor_user_id)
                | (GuardianStudentLink.student_user_id == actor_user_id),
            ))
            if link is None:
                return False
            link.status = "revoked"
            return True

    def list_guardian_links(self, user_id: str, role: str) -> list[GuardianLinkResponse]:
        with self.session_factory() as db:
            criterion = (
                GuardianStudentLink.guardian_user_id == user_id
                if role == "guardian"
                else GuardianStudentLink.student_user_id == user_id
            )
            links = db.scalars(
                select(GuardianStudentLink)
                .where(criterion)
                .order_by(GuardianStudentLink.created_at.desc())
            ).all()
            return [self._link_response(db, link) for link in links]

    def guardian_can_access(self, guardian_user_id: str, student_user_id: str) -> bool:
        with self.session_factory() as db:
            link_id = db.scalar(select(GuardianStudentLink.id).where(
                GuardianStudentLink.guardian_user_id == guardian_user_id,
                GuardianStudentLink.student_user_id == student_user_id,
                GuardianStudentLink.status == "active",
            ))
            return link_id is not None

    @staticmethod
    def to_identity(user: User) -> AuthenticatedUser:
        if user.student_profile is not None:
            return AuthRepository._identity(
                user,
                user.student_profile.display_name,
                user.student_profile.grade_band,
            )
        if user.guardian_profile is not None:
            return AuthRepository._identity(user, user.guardian_profile.display_name, None)
        return AuthRepository._identity(user, user.email.split("@", 1)[0], None)

    @staticmethod
    def _identity(
        user: User,
        display_name: str,
        grade_band: str | None,
    ) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=user.id,
            email=user.email,
            role=user.role,
            account_status=user.account_status,
            token_version=user.token_version,
            display_name=display_name,
            grade_band=grade_band,
            email_verified=user.email_verified_at is not None,
        )

    @staticmethod
    def _user_query():
        return select(User).options(
            selectinload(User.student_profile),
            selectinload(User.guardian_profile),
        )

    @staticmethod
    def _link_response(db: Session, link: GuardianStudentLink) -> GuardianLinkResponse:
        guardian = db.get(GuardianProfile, link.guardian_user_id)
        student = db.get(StudentProfile, link.student_user_id)
        return GuardianLinkResponse(
            id=link.id,
            guardian_user_id=link.guardian_user_id,
            student_user_id=link.student_user_id,
            guardian_name=guardian.display_name if guardian else "家长",
            student_name=student.display_name if student else "学生",
            relationship=link.relationship_type,
            status=link.status,
            consented_at=AuthRepository._to_utc(link.consented_at),
            created_at=AuthRepository._to_utc(link.created_at),
        )

    @staticmethod
    def _to_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _revoke_refresh_family(db: Session, family_id: str, now: datetime) -> None:
        db.execute(update(RefreshSession).where(
            RefreshSession.family_id == family_id,
            RefreshSession.revoked_at.is_(None),
        ).values(revoked_at=now))

    @staticmethod
    def _revoke_user_refresh_sessions(db: Session, user_id: str, now: datetime) -> None:
        db.execute(update(RefreshSession).where(
            RefreshSession.user_id == user_id,
            RefreshSession.revoked_at.is_(None),
        ).values(revoked_at=now))
