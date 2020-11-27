# Standart python libs
from os import environ
# apscheduler
from apscheduler.schedulers.background import BackgroundScheduler
# Pyrogram
from pyrogram import Client, filters, idle, raw
from pyrogram.types import Message, Chat
import pyrogram.errors
# pymongo
from pymongo import MongoClient
import pymongo.errors


# Pyrogram init
user = Client(environ.get('SESSION_STRING'), environ.get('API_ID'), environ.get('API_HASH'))    # TODO: Нормальный стораж сессий
bot = Client(':memory:', environ.get('API_ID'), environ.get('API_HASH'), bot_token=environ.get('BOT_TOKEN'))
user_id = 0

# Mongo init
mongo_client = MongoClient(environ.get('MONGODB_STRING') or 'mongodb://localhost:27017')
db = mongo_client['pieradopis-cian']
channels = db['channels']
chats = db['chats']


def check_updates():
    for channel in channels.find():
        min_message_id = min([chat['lastMessageId'] for chat in channel['chats']])
        msg_ids = [m.message_id for m in user.iter_history(channel['_id'], offset_id=min_message_id, reverse=True)]
        if len(msg_ids) == 1:
            continue
        for chat in channel['chats']:
            forwarded_messages = user.forward_messages(
                environ.get('BOT_USERNAME'),
                channel['_id'],
                [msg_id for msg_id in msg_ids if msg_id > chat['lastMessageId']]
            )
            # TODO: GET BOT UPDATES HERE
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


@bot.on_message(filters.command(['start', f'start@{environ.get("BOT_USERNAME")}']))
def on_start(client: Client, message: Message):
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
                      'Дадаць канал: /add_channel\n'
                      'Кіраванне каналамі: /channels\n'
                      'Іншыя налады: /settings')
    except pymongo.errors.DuplicateKeyError:
        message.reply('Бот ужо праініцыялізаваны для гэтага чата. Вы дакладна хочаеце праініцыялізаваць яго зноў?\n'
                      '**Увага: гэта скіне ўсе налады.**')
    except Exception as e:
        print(e)
        message.reply('Не атрымалася праініцыялізаваць бота для гэтага чата.\n'
                      'Паспрабуйце яшчэ раз.\n'
                      'Калі вы спрабуеце не першы раз — больш не спрабуйце, думаю, гэта не дапаможа.')


@bot.on_message(filters.command(['add_channel', f'add_channel@{environ.get("BOT_USERNAME")}']))
def on_add_channel(client: Client, message: Message):
    if message.chat.type in ('group', 'supergroup'):
        if message.from_user.id != 1423463788:
            if client.get_chat_member(message.chat.id, message.from_user.id).status not in ('administrator', 'creator'):
                return
    if message.text.replace('/add_channel', '').replace(f'@{environ.get("BOT_USERNAME")}', '').strip() == '':
        message.reply('Калі ласка, выкарыстоўвайце `/add_channel @channel`')
        return
    channel_id = message.text.replace('/add_channel', '').replace(f'@{environ.get("BOT_USERNAME")}', '').strip()
    try:
        channel: Chat = user.get_chat(channel_id)
        if channel.type != 'channel':
            message.reply('Гэта не канал')
            return
        channel_last_message_id = user.get_history(channel.id, 1)[0].message_id
        if channel.id in chats.find_one({'_id': message.chat.id})['channels']:
            message.reply('Гэты канал ужо дадазены')
            return
        chats.update_one(
            {
                '_id': message.chat.id
            },
            {
                '$push': {
                    'channels': channel.id
                }
            }
        )
        channels.update_one(
            {
                '_id': channel.id
            },
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
        message.reply('Канал быў паспяхова дададзены')
    except pyrogram.errors.UsernameInvalid as e:
        message.reply('Не атрымалася знайсці такі канал.')


if __name__ == '__main__':
    bot.start()
    # state = bot.send(raw.functions.updates.GetState())
    # print(bot.send(raw.functions.updates.GetDifference(pts=state['pts'], date=state['date'], qts=state['qts'])))
    user.start()
    user_id = user.get_me().id
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_updates, "interval", seconds=5)
    scheduler.start()
    print('started')
    idle()
