from telethon import TelegramClient
import asyncio

# Replace with your own credentials from https://my.telegram.org
api_id = 23008284       # your API ID
api_hash = '9b753f6de26369ddff1f498ce4d21fb5'  # your API hash
phone = '+94781440205'       # your phone number (with country code)

# Replace with your group and topic IDs
group_id = -1002039861131   # example group ID (must be negative for supergroups)
topic_id = 40011             # the topic/thread ID in the group

async def main():
    # Initialize the client
    client = TelegramClient('session_name', api_id, api_hash)
    await client.start(phone=phone)

    print(f"Fetching messages from group {group_id}, topic {topic_id}...")
    
    # Iterate over messages in the topic
    async for message in client.iter_messages(group_id, reply_to=topic_id, limit=100):
        sender = await message.get_sender()
        sender_name = sender.first_name if sender else "Unknown"
        print(f"[{message.date}] {sender_name}: {message.text}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
