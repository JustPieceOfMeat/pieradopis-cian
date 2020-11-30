# Standard python libs
from os import environ
from typing import List, Iterable
# apscheduler
from apscheduler.schedulers.background import BackgroundScheduler
# Pyrogram
from pyrogram import Client, filters, idle
from pyrogram.types import Message, Chat, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import pyrogram.errors
# pymongo
from pymongo import MongoClient
import pymongo.errors


# Pyrogram init
user = Client(
    '/sessions/user' if environ.get('DOCKER') else (environ.get('SESSION_NAME') or 'my_account'),
    environ.get('API_ID'),
    environ.get('API_HASH')
)
bot = Client(':memory:', environ.get('API_ID'), environ.get('API_HASH'), bot_token=environ.get('BOT_TOKEN'))

# Mongo init
mongo_client = MongoClient(environ.get('MONGODB_STRING') or 'mongodb://localhost:27017')
db = mongo_client['pieradopis-cian']
channels = db['channels']
chats = db['chats']

# Other variables
user_id = int(environ.get('USER_ID'))
bot_messages_ids: List[int] = []


def check_updates():
    for channel in channels.find():
        if len(channel['chats']) < 1:
            continue
        min_message_id = min([chat['lastMessageId'] for chat in channel['chats']])
        # noinspection PyTypeChecker
        messages: List[Message] = \
            [message for message in user.iter_history(channel['_id'], offset_id=min_message_id, reverse=True)
             if not message.service]
        msg_ids = [m.message_id for m in messages if 'NOT_FOR_FORWARD' not in ' '.join([str(m.text), str(m.caption)])]
        no_nsfw_msg_ids = [m.message_id for m in messages if 'NSFW' not in ' '.join([str(m.text), str(m.caption)]) and
                           'NOT_FOR_FORWARD' not in ' '.join([str(m.text), str(m.caption)])]
        if len(msg_ids) == 1:
            continue
        for chat in channel['chats']:
            forwarded_messages: List[Message] = []
            if chats.find_one({'_id': chat['chatId']})['NSFW']:
                # noinspection PyTypeChecker
                forwarded_messages = user.forward_messages(
                    environ.get('BOT_USERNAME'),
                    channel['_id'],
                    [msg_id for msg_id in msg_ids if msg_id > chat['lastMessageId']]
                )
            elif len(no_nsfw_msg_ids) > 1:
                # noinspection PyTypeChecker
                forwarded_messages = user.forward_messages(
                    environ.get('BOT_USERNAME'),
                    channel['_id'],
                    [msg_id for msg_id in no_nsfw_msg_ids if msg_id > chat['lastMessageId']]
                )
            global bot_messages_ids
            while len(bot_messages_ids) != len(forwarded_messages):
                pass
            if len(bot_messages_ids) > 0:
                bot.forward_messages(
                    chat['chatId'],
                    user_id,
                    bot_messages_ids,
                    as_copy=chats.find_one({'_id': chat['chatId']})['asCopy']
                )
                bot_messages_ids = []
                user.delete_messages(
                    environ.get('BOT_USERNAME'),
                    [message.message_id for message in forwarded_messages]
                )
            channels.update_one(
                {
                    '_id': channel['_id'],
                    'chats.chatId': chat['chatId']
                },
                {
                    '$set': {
                        'chats.$.lastMessageId': max(msg_ids)
                    }
                }
            )


@bot.on_message(filters.command('start'))
def on_start(client: Client, message: Message):
    print('Вітаю, я працую толькі ў чатах. Дадай мяне ў любы чат і напішы /init каб праініцыялізаваць.')


@bot.on_message(filters.command(['init', f'init@{environ.get("BOT_USERNAME")}']) & filters.group)
def on_init(client: Client, message: Message):
    if message.chat.type in ('group', 'supergroup'):
        if message.from_user.id != 1423463788:
            if client.get_chat_member(message.chat.id, message.from_user.id).status not in ('administrator', 'creator'):
                return
    try:
        chats.insert_one({
            '_id': message.chat.id,
            'channels': [],
            'language': 'BY',
            'asCopy': False,
            'signPosts': False
        })
        message.reply('Бот паспяхова ініцыялізаваны для гэтага чату.\n'
                      'Прывязаць канал: /link @channel\n'
                      'Паглядзець спіс прывязаных каналаў: /channels\n'
                      'двязаць канал: /unlink @channel'
                      'Іншыя налады: /settings')
    except pymongo.errors.DuplicateKeyError:
        message.reply('Бот ужо праініцыялізаваны для гэтага чата.')
    except Exception as e:
        print(e)
        message.reply('Не атрымалася праініцыялізаваць бота для гэтага чата.\n'
                      'Паспрабуйце яшчэ раз.\n'
                      'Калі вы спрабуеце не першы раз — больш не спрабуйце, думаю, гэта не дапаможа.')


@bot.on_message(filters.command(['link', f'link@{environ.get("BOT_USERNAME")}']) & filters.group)
def on_link(client: Client, message: Message):
    if message.chat.type in ('group', 'supergroup'):
        if message.from_user.id != 1423463788:
            if client.get_chat_member(message.chat.id, message.from_user.id).status not in ('administrator', 'creator'):
                return
    if message.text.replace('/link', '').replace(f'@{environ.get("BOT_USERNAME")}', '').strip() == '':
        message.reply('Калі ласка, выкарыстоўвайце `/link @channel`')
        return
    channel_id = message.text.replace('/link', '').replace(f'@{environ.get("BOT_USERNAME")}', '').strip()
    try:
        # noinspection PyTypeChecker
        channel: Chat = user.get_chat(channel_id)
        if channel.type != 'channel':
            message.reply('Гэта не канал')
            return
        channel_last_message_id = user.get_history(channel.id, 1)[0].message_id
        if channel.id in chats.find_one({'_id': message.chat.id})['channels']:
            message.reply('Гэты канал ужо прывязаны')
            return
        chats.update_one(
            {'_id': message.chat.id},
            {'$push': {'channels': channel.id}}
        )
        channels.update_one(
            {'_id': channel.id},
            {
                '$push': {
                    'chats': {
                        'chatId': message.chat.id,
                        'lastMessageId': channel_last_message_id
                    }
                }
            },
            True
        )
        message.reply('Канал быў паспяхова прывязаны')
    except pyrogram.errors.UsernameInvalid:
        message.reply('Не атрымалася знайсці такі канал.')


@bot.on_message(filters.command(['channels', f'channels@{environ.get("BOT_USERNAME")}']) & filters.group)
def on_channels(client: Client, message: Message):
    if message.chat.type in ('group', 'supergroup'):
        if message.from_user.id != 1423463788:
            if client.get_chat_member(message.chat.id, message.from_user.id).status not in ('administrator', 'creator'):
                return
    # noinspection PyTypeChecker
    sent_message: Message = message.reply('Пачакайце, калі ласка…')
    channel_usernames: List[str] = []
    for channel in chats.find_one({'_id': message.chat.id})['channels']:
        channel_usernames.append(user.get_chat(channel).username)
    sent_message.edit_text('Спіс прывязанных каналаў:\n' + '\n'.join(['@' + name for name in channel_usernames]))


@bot.on_message(filters.command(['unlink', f'unlink@{environ.get("BOT_USERNAME")}']) & filters.group)
def on_unlink(client: Client, message: Message):
    if message.chat.type in ('group', 'supergroup'):
        if message.from_user.id != 1423463788:
            if client.get_chat_member(message.chat.id, message.from_user.id).status not in ('administrator', 'creator'):
                return
    if message.text.replace('/unlink', '').replace(f'@{environ.get("BOT_USERNAME")}', '').strip() == '':
        message.reply('Калі ласка, выкарыстоўвайце `/unlink @channel`')
        return
    channel_id = message.text.replace('/unlink', '').replace(f'@{environ.get("BOT_USERNAME")}', '').strip()
    try:
        # noinspection PyTypeChecker
        channel: Chat = user.get_chat(channel_id)
        if channel.type != 'channel':
            message.reply('Гэта не канал')
            return
        if channel.id not in chats.find_one({'_id': message.chat.id})['channels']:
            message.reply('Гэты канал не прывязаны')
            return
        chats.update_one(
            {'_id': message.chat.id},
            {'$pull': {'channels': channel.id}}
        )
        channels.update_one(
            {'_id': channel.id},
            {'$pull': {'chats': {'chatId': message.chat.id}}},
            True
        )
        message.reply('Канал быў паспяхова адвязаны')
    except pyrogram.errors.UsernameInvalid:
        message.reply('Не атрымалася знайсці такі канал.')


def generate_settings_markup(chat_id) -> InlineKeyboardMarkup:
    chat = chats.find_one({'_id': chat_id})
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"Капіяваць: {'Так' if chat['asCopy'] else 'Не'}",
            'dont_copy' if chat['asCopy'] else 'copy'
        )],
        # [InlineKeyboardButton(
        #     f"Дадаваць подпіс: {'Так' if chat['asCopy'] else 'Не'}",
        #     'dont_sign' if chat['sign'] else 'sign'
        # )],
        [InlineKeyboardButton(
            f"NSFW: {'Так' if chat['NSFW'] else 'Не'}",
            'dont_send_NSFW' if chat['NSFW'] else 'send_NSFW'
        )],
    ])


@bot.on_message(filters.command(['settings', f'settings@{environ.get("BOT_USERNAME")}']))
def on_settings(_: Client, message: Message):
    message.reply('Налады', reply_markup=generate_settings_markup(message.chat.id))


@bot.on_callback_query()
def on_callback(_: Client, callback: CallbackQuery):
    if callback.data == 'copy':
        chats.update_one(
            {'_id': callback.message.chat.id},
            {'$set': {'asCopy': True}}
        )
    elif callback.data == 'dont_copy':
        chats.update_one(
            {'_id': callback.message.chat.id},
            {
                '$set': {
                    'asCopy': False,
                    'signPosts': False
                }
            }
        )
    elif callback.data == 'send_NSFW':
        chats.update_one(
            {'_id': callback.message.chat.id},
            {'$set': {'NSFW': True}}
        )
    elif callback.data == 'dont_send_NSFW':
        chats.update_one(
            {'_id': callback.message.chat.id},
            {'$set': {'NSFW': False}}
        )
    callback.message.edit_reply_markup(generate_settings_markup(callback.message.chat.id))


@bot.on_message(filters.chat(user_id))
def on_message_from_user(_: Client, message: Message):
    bot_messages_ids.append(message.message_id)


if __name__ == '__main__':
    bot.start()
    user.start()
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_updates, "interval", seconds=60)
    scheduler.start()
    idle()
