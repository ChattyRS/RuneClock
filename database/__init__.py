from gino import Gino
import codecs
import json

'''
Load config file with necessary information
'''
def config_load():
    with codecs.open('data/config.json', 'r', encoding='utf-8-sig') as doc:
        #  Please make sure encoding is correct, especially after editing the config file
        return json.load(doc)

db = Gino()

class User(db.Model):  
    __tablename__ = 'users'

    id = db.Column(db.BigInteger, primary_key=True)
    rsn = db.Column(db.String)
    osrs_rsn = db.Column(db.String)
    timezone = db.Column(db.String)

class Guild(db.Model):
    __tablename__ = 'guilds'

    id = db.Column(db.BigInteger, primary_key=True)
    prefix = db.Column(db.String)
    welcome_channel_id = db.Column(db.BigInteger)
    welcome_message = db.Column(db.String)
    rs3_news_channel_id = db.Column(db.BigInteger)
    osrs_news_channel_id = db.Column(db.BigInteger)
    log_channel_id = db.Column(db.BigInteger)
    notification_channel_id = db.Column(db.BigInteger)
    role_channel_id = db.Column(db.BigInteger)
    delete_channel_ids = db.Column(db.ARRAY(db.BigInteger))
    disabled_commands = db.Column(db.ARRAY(db.String))
    log_bots = db.Column(db.Boolean)
    modmail_public = db.Column(db.BigInteger)
    modmail_private = db.Column(db.BigInteger)

class Role(db.Model):
    __tablename__ = 'roles'

    guild_id = db.Column(db.BigInteger, db.ForeignKey('guilds.id'), nullable=False)
    name = db.Column(db.String)
    role_id = db.Column(db.BigInteger)

    _pk = db.PrimaryKeyConstraint('guild_id', 'name', name='role_pkey')

class Mute(db.Model):
    __tablename__ = 'mutes'

    guild_id = db.Column(db.BigInteger, db.ForeignKey('guilds.id'), nullable=False)
    user_id = db.Column(db.BigInteger)
    expiration = db.Column(db.DateTime)
    reason = db.Column(db.String)

    _pk = db.PrimaryKeyConstraint('guild_id', 'user_id', name='mute_pkey')

class Command(db.Model):
    __tablename__ = 'commands'

    guild_id = db.Column(db.BigInteger, db.ForeignKey('guilds.id'), nullable=False)
    name = db.Column(db.String)
    function = db.Column(db.String)
    aliases = db.Column(db.ARRAY(db.String))
    description = db.Column(db.String)

    _pk = db.PrimaryKeyConstraint('guild_id', 'name', name='command_pkey')

class Repository(db.Model):
    __tablename__ = 'repositories'

    guild_id = db.Column(db.BigInteger, db.ForeignKey('guilds.id'), nullable=False)
    channel_id = db.Column(db.BigInteger)
    user_name = db.Column(db.String)
    repo_name = db.Column(db.String)
    sha = db.Column(db.String)

    _pk = db.PrimaryKeyConstraint('guild_id', 'user_name', 'repo_name', name='repo_pkey')

class Notification(db.Model):
    __tablename__ = 'notifications'

    guild_id = db.Column(db.BigInteger, db.ForeignKey('guilds.id'), nullable=False)
    notification_id = db.Column(db.Integer)
    channel_id = db.Column(db.BigInteger)
    time = db.Column(db.DateTime)
    interval = db.Column(db.Integer)
    message = db.Column(db.String)

    _pk = db.PrimaryKeyConstraint('guild_id', 'notification_id', name='notification_pkey')

class OnlineNotification(db.Model):
    __tablename__ = 'online_notifications'

    guild_id = db.Column(db.BigInteger, db.ForeignKey('guilds.id'), nullable=False)
    author_id = db.Column(db.BigInteger)
    member_id = db.Column(db.BigInteger)
    channel_id = db.Column(db.BigInteger)
    type = db.Column(db.Integer)

    _pk = db.PrimaryKeyConstraint('guild_id', 'author_id', 'member_id', name='online_notification_pkey')

class Poll(db.Model):
    __tablename__ = 'polls'

    guild_id = db.Column(db.BigInteger, db.ForeignKey('guilds.id'), nullable=False)
    author_id = db.Column(db.BigInteger)
    channel_id = db.Column(db.BigInteger)
    message_id = db.Column(db.BigInteger)
    end_time = db.Column(db.DateTime)

    _pk = db.PrimaryKeyConstraint('guild_id', 'message_id', name='poll_pkey')

class NewsPost(db.Model):
    __tablename__ = 'news_posts'

    link = db.Column(db.String, primary_key=True)
    game = db.Column(db.String)
    title = db.Column(db.String)
    description = db.Column(db.String)
    time = db.Column(db.DateTime)
    category = db.Column(db.String)
    image_url = db.Column(db.String)

class Uptime(db.Model):
    __tablename__ = 'uptime'

    time = db.Column(db.DateTime, primary_key=True)
    status = db.Column(db.String)

class RS3Item(db.Model):
    __tablename__ = 'rs3_items'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    icon_url = db.Column(db.String)
    type = db.Column(db.String)
    description = db.Column(db.String)
    members = db.Column(db.Boolean)
    current = db.Column(db.String)
    today = db.Column(db.String)
    day30 = db.Column(db.String)
    day90 = db.Column(db.String)
    day180 = db.Column(db.String)
    graph_data = db.Column(db.JSON)

# https://rsbuddy.com/exchange/summary.json
class OSRSItem(db.Model):
    __tablename__ = 'osrs_items'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    icon_url = db.Column(db.String)
    type = db.Column(db.String)
    description = db.Column(db.String)
    members = db.Column(db.Boolean)
    current = db.Column(db.String)
    today = db.Column(db.String)
    day30 = db.Column(db.String)
    day90 = db.Column(db.String)
    day180 = db.Column(db.String)
    graph_data = db.Column(db.JSON)

async def setup():
    config = config_load()
    await db.set_bind(f'postgresql+asyncpg://{config["postgres_username"]}:{config["postgres_password"]}@{config["postgres_ip"]}:{config["postgres_port"]}/gino')

async def close_connection():
    await db.pop_bind().close()