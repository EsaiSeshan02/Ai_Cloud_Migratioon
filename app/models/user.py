from flask_login import UserMixin

from app.extensions import db
from app.utils.time import UTCDateTime, utc_now

class User(
    UserMixin,
    db.Model
):

    __tablename__ = "users"


    id = db.Column(

        db.Integer,

        primary_key=True

    )


    name = db.Column(

        db.String(100),

        nullable=False

    )


    email = db.Column(

        db.String(120),

        unique=True,

        nullable=False

    )


    password_hash = db.Column(

        db.String(255),

        nullable=False

    )


    created_at = db.Column(

        UTCDateTime(),

        default=utc_now

    )

    migrations = db.relationship("Migration", backref="user", lazy=True)
    migration_plans = db.relationship("MigrationPlan", backref="owner", lazy=True)
    reports = db.relationship("Report", backref="owner", lazy=True)


    def get_id(self):

        return str(

            self.id

        )
