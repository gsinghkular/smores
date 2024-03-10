import settings
import logging

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


from slack_sdk.oauth.installation_store.sqlalchemy import SQLAlchemyInstallationStore
from slack_sdk.oauth.state_store.sqlalchemy import SQLAlchemyOAuthStateStore


logger = logging.getLogger(__name__)


engine = create_engine(settings.DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


installation_store = SQLAlchemyInstallationStore(
    client_id=settings.SLACK_CLIENT_ID,
    engine=engine,
    logger=logger,
)
oauth_state_store = SQLAlchemyOAuthStateStore(
    expiration_seconds=120,
    engine=engine,
    logger=logger,
)

Base = declarative_base()

for dec_base in [installation_store, oauth_state_store]:
    for (table_name, table) in dec_base.metadata.tables.items():
        Base.metadata._add_table(table_name, table.schema, table)
