from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

db = SQLAlchemy()

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return f'<Setting {self.key}>'

class MonitoredGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<MonitoredGroup {self.name}>'
class AzureDevOpsConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization_name = db.Column(db.String(100), nullable=False, unique=True) # Zmieniono z organization_url i dodano unique
    pat_token = db.Column(db.String(200), nullable=False)
    monitored_pools = db.relationship('MonitoredADOPool', backref='organization', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<AzureDevOpsConfig {self.organization_name}>'

class MonitoredADOPool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pool_id = db.Column(db.Integer, nullable=False)
    pool_name = db.Column(db.String(100), nullable=False)
    ado_config_id = db.Column(db.Integer, db.ForeignKey('azure_dev_ops_config.id'), nullable=False)

    def __repr__(self):
        return f'<MonitoredADOPool {self.pool_name}>'

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'
