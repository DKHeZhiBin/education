from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.core.logging import configure_cli_logging
from app.core.config import settings
from app.core.database import create_mysql_engine, create_session_factory
from app.core.security import hash_password, verify_password
from app.models import (
    AccountActionToken,
    GuardianProfile,
    GuardianStudentLink,
    RefreshSession,
    StudentProfile,
    User,
)


DEMO_PASSWORD = "MathTutorDemo2026!"


@dataclass(frozen=True)
class DemoAccount:
    """中文：定义“demo·account”类，封装该职责相关的数据与行为。
    English: Defines the demo account class and encapsulates data and behavior for that responsibility.
    """
    email: str
    role: str
    display_name: str


DEMO_ACCOUNTS = (
    DemoAccount("student.demo@example.com", "student", "演示学生"),
    DemoAccount("guardian.demo@example.com", "guardian", "演示家长"),
    DemoAccount("admin.demo@example.com", "admin", "知识管理员"),
)


def main() -> None:
    """中文：处理“main”相关操作。
    English: Handles the main operation.
    """
    configure_cli_logging()
    if settings.app_env != "development":
        raise SystemExit("Demo accounts can only be initialized in APP_ENV=development")

    engine = create_mysql_engine()
    session_factory = create_session_factory(engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    account_ids: dict[str, str] = {}

    try:
        with session_factory.begin() as db:
            for account in DEMO_ACCOUNTS:
                user = db.scalar(
                    select(User).where(User.email == account.email).with_for_update()
                )
                if user is None:
                    user = User(
                        email=account.email,
                        password_hash=hash_password(DEMO_PASSWORD),
                        role=account.role,
                        account_status="active",
                        token_version=1,
                        email_verified_at=now,
                    )
                    db.add(user)
                    db.flush()
                    credentials_restored = False
                else:
                    if user.role != account.role:
                        raise RuntimeError(
                            f"Demo email {account.email} already belongs to role {user.role}"
                        )
                    password_matches = verify_password(DEMO_PASSWORD, user.password_hash)
                    credentials_restored = (
                        not password_matches
                        or user.account_status != "active"
                        or user.deleted_at is not None
                    )
                    if not password_matches:
                        user.password_hash = hash_password(DEMO_PASSWORD)
                    user.account_status = "active"
                    user.email_verified_at = now
                    user.deleted_at = None
                    if credentials_restored:
                        user.token_version += 1

                if credentials_restored:
                    db.execute(delete(AccountActionToken).where(
                        AccountActionToken.user_id == user.id
                    ))
                    db.execute(delete(RefreshSession).where(
                        RefreshSession.user_id == user.id
                    ))

                if account.role == "student":
                    profile = db.get(StudentProfile, user.id)
                    if profile is None:
                        db.add(StudentProfile(
                            user_id=user.id,
                            display_name=account.display_name,
                            grade_band="university",
                        ))
                    else:
                        profile.display_name = account.display_name
                        profile.grade_band = "university"
                elif account.role == "guardian":
                    profile = db.get(GuardianProfile, user.id)
                    if profile is None:
                        db.add(GuardianProfile(
                            user_id=user.id,
                            display_name=account.display_name,
                        ))
                    else:
                        profile.display_name = account.display_name

                # 中文：管理员不需要学生或家长扩展档案。 English: Administrators do not need student or guardian profile rows.

                account_ids[account.role] = user.id

            db.flush()
            link = db.scalar(select(GuardianStudentLink).where(
                GuardianStudentLink.guardian_user_id == account_ids["guardian"],
                GuardianStudentLink.student_user_id == account_ids["student"],
            ))
            if link is None:
                db.add(GuardianStudentLink(
                    guardian_user_id=account_ids["guardian"],
                    student_user_id=account_ids["student"],
                    relationship_type="guardian",
                    status="active",
                    consented_at=now,
                ))
            else:
                link.status = "active"
                link.consented_at = now
    finally:
        engine.dispose()

    print("Development demo accounts are ready:")
    for account in DEMO_ACCOUNTS:
        print(f"- {account.role}: {account.email}")


if __name__ == "__main__":
    main()
