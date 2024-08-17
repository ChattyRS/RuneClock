from sqlite3 import Date
from sqlalchemy import MetaData, Table, Column, PrimaryKeyConstraint, ForeignKey
from sqlalchemy import BigInteger, Integer, String, Boolean, DateTime, ARRAY, JSON
import codecs
import json

'''
Load config file with necessary information
'''
def config_load():
    with codecs.open('data/config.json', 'r', encoding='utf-8-sig') as doc:
        #  Please make sure encoding is correct, especially after editing the config file
        return json.load(doc)

metadata_obj = MetaData()

users = Table(
    'users',
    metadata_obj,
    Column('id', BigInteger, primary_key=True),
    Column('rsn', String),
    Column('osrs_rsn', String),
    Column('timezone', String)
)

guilds = Table(
    'guilds',
    metadata_obj,
    Column('id', BigInteger, primary_key=True),
    Column('prefix', String(100)),
    Column('welcome_channel_id', BigInteger),
    Column('welcome_message', String),
    Column('rs3_news_channel_id', BigInteger),
    Column('osrs_news_channel_id', BigInteger),
    Column('log_channel_id', BigInteger),
    Column('notification_channel_id', BigInteger),
    Column('role_channel_id', BigInteger),
    Column('delete_channel_ids', ARRAY(BigInteger)),
    Column('disabled_commands', ARRAY(String)),
    Column('log_bots', Boolean),
    Column('modmail_public', BigInteger),
    Column('modmail_private', BigInteger),
    Column('hall_of_fame_channel_id', BigInteger),
    Column('hall_of_fame_react_num', BigInteger),
    Column('bank_role_id', BigInteger),
    Column('wom_role_id', BigInteger),
    Column('wom_group_id', BigInteger),
    Column('wom_verification_code', String),
    Column('wom_excluded_metrics', String),
    Column('custom_role_reaction_channel_id', BigInteger),
    Column('role_reaction_management_role_id', BigInteger),
    Column('custom_role_reaction_message', String)
)

roles = Table(
    'roles',
    metadata_obj,
    Column('guild_id', BigInteger, ForeignKey('guilds.id'), nullable=False),
    Column('name', String),
    Column('role_id', BigInteger),

    PrimaryKeyConstraint('guild_id', 'name', name='role_pkey')
)

mutes = Table(
    'mutes',
    metadata_obj,
    Column('guild_id', BigInteger, ForeignKey('guilds.id'), nullable=False),
    Column('user_id', BigInteger),
    Column('expiration', DateTime),
    Column('reason', String),

    PrimaryKeyConstraint('guild_id', 'user_id', name='mute_pkey')
)

commands = Table(
    'commands',
    metadata_obj,
    Column('guild_id', BigInteger, ForeignKey('guilds.id'), nullable=False),
    Column('name', String),
    Column('function', String),
    Column('aliases', ARRAY(String)),
    Column('description', String),

    PrimaryKeyConstraint('guild_id', 'name', name='command_pkey')
)

repositories = Table(
    'repositories',
    metadata_obj,
    Column('guild_id', BigInteger, ForeignKey('guilds.id'), nullable=False),
    Column('channel_id', BigInteger),
    Column('user_name', String),
    Column('repo_name', String),
    Column('sha', String),

    PrimaryKeyConstraint('guild_id', 'user_name', 'repo_name', name='repo_pkey')
)

notifications = Table(
    'notifications',
    metadata_obj,
    Column('guild_id', BigInteger, ForeignKey('guilds.id'), nullable=False),
    Column('notification_id', Integer),
    Column('channel_id', BigInteger),
    Column('time', DateTime),
    Column('interval', Integer),
    Column('message', String),

    PrimaryKeyConstraint('guild_id', 'notification_id', name='notification_pkey')
)

online_notifications = Table(
    'online_notifications',
    metadata_obj,
    Column('guild_id', BigInteger, ForeignKey('guilds.id'), nullable=False),
    Column('author_id', BigInteger),
    Column('member_id', BigInteger),
    Column('channel_id', BigInteger),
    Column('type', Integer),

    PrimaryKeyConstraint('guild_id', 'author_id', 'member_id', name='online_notification_pkey')
)

polls = Table(
    'polls',
    metadata_obj,
    Column('guild_id', BigInteger, ForeignKey('guilds.id'), nullable=False),
    Column('author_id', BigInteger),
    Column('channel_id', BigInteger),
    Column('message_id', BigInteger),
    Column('end_time', DateTime),

    PrimaryKeyConstraint('guild_id', 'message_id', name='poll_pkey')
)

news_posts = Table(
    'news_posts',
    metadata_obj,
    Column('link', String, primary_key=True),
    Column('game', String),
    Column('title', String),
    Column('description', String),
    Column('time', DateTime),
    Column('category', String),
    Column('image_url', String),
)

uptime = Table(
    'uptime',
    metadata_obj,
    Column('time', DateTime, primary_key=True),
    Column('status', String)
)

rs3_items = Table(
    'rs3_items',
    metadata_obj,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('icon_url', String),
    Column('type', String),
    Column('description', String),
    Column('members', Boolean),
    Column('current', String),
    Column('today', String),
    Column('day30', String),
    Column('day90', String),
    Column('day180', String),
    Column('graph_data', JSON),
)

osrs_items = Table(
    'osrs_items',
    metadata_obj,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('icon_url', String),
    Column('type', String),
    Column('description', String),
    Column('members', Boolean),
    Column('current', String),
    Column('today', String),
    Column('day30', String),
    Column('day90', String),
    Column('day180', String),
    Column('graph_data', JSON),
)

clan_bank_transactions = Table(
    'clan_bank_transactions',
    metadata_obj,
    Column('id', Integer, primary_key=True),
    Column('guild_id', BigInteger, ForeignKey('guilds.id'), nullable=False),
    Column('member_id', BigInteger, nullable=False),
    Column('time', DateTime, nullable=False),
    Column('amount', BigInteger, nullable=False),
    Column('description', String),
)

custom_role_reactions = Table(
    'custom_role_reactions',
    metadata_obj,
    Column('id', BigInteger, primary_key=True),
    Column('guild_id', BigInteger, ForeignKey('guilds.id'), nullable=False),
    Column('emoji_id', BigInteger, nullable=False),
    Column('role_id', BigInteger, nullable=False),
)

banned_guilds = Table(
    'banned_guilds',
    metadata_obj,
    Column('id', BigInteger, primary_key=True),
    Column('name', String),
    Column('reason', String),
)

async def setup():
    print('Setting up database connection...')
    config = config_load()
    await db.set_bind(f'postgresql+asyncpg://{config["postgres_username"]}:{config["postgres_password"]}@{config["postgres_ip"]}:{config["postgres_port"]}/{config["postgres_db_name"]}')
    await db.gino.create_all()
    print('Database ready!')

async def close_connection():
    await db.pop_bind().close()