import asyncio
from bot import bot, log
from bot.commands import FuriganaCog


async def main():
    async with bot:
        await bot.add_cog(FuriganaCog(bot))
        with open("bot_token.txt", "r") as f:
            token = f.read().strip()
        log.info("Starting bot")
        await bot.start(token)


asyncio.run(main())
