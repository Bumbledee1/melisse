
# Imports
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import csv
from typing import List

# Bot Settings
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# Category IDs
TICKET_CATEGORY_ID = 1365516765152415866
CART_CATEGORY_ID = 1336017251618263082
RECEIPT_CATEGORY_ID = 1365680710215667773
ORDERS_CATEGORY_ID = 1365661620667154502

# Temporary product data storage
pending_products = {}
carts = {}  # user_id -> list of product embeds

# Persistent Views registration

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component and interaction.data.get("custom_id") == "persistent_close_cart":
        if interaction.user.guild_permissions.administrator:
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("❌ You don't have permission to close this cart.", ephemeral=True)
    return
    print(f"Logged in as {bot.user}")

# Views (Buttons / Modals)

class WishlistButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="💖 Add to Wishlist",
            style=discord.ButtonStyle.primary,
            custom_id="persistent_addtowishlist",
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.message.attachments:
            await interaction.response.send_message("⚠️ No product image found.", ephemeral=True)
            return

        file = interaction.message.attachments[0]
        parts = interaction.message.content.split(" - $")
        product_name = parts[0] if parts else "Unnamed Product"
        product_price = parts[1] if len(parts) > 1 else "Unknown"

        embed = discord.Embed(title=f"💖 {product_name}", color=discord.Color.pink())
        embed.add_field(name="💰 Price", value=product_price)
        embed.set_image(url=file.url)
        embed.set_footer(text="Click below to view the product on the server")

        view_button = discord.ui.View()
        view_button.add_item(discord.ui.Button(label="🔗 View Product", style=discord.ButtonStyle.link, url=interaction.message.jump_url))

        try:
            await interaction.user.send("📥 Added to your wishlist:", embed=embed, view=view_button)
            await interaction.response.send_message("✅ Sent to your wishlist in DM!", ephemeral=True)
        except:
            await interaction.response.send_message("⚠️ Could not send wishlist item to your DMs. Please check your privacy settings.", ephemeral=True)

class AddToCartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(WishlistButton())

    
    @discord.ui.button(label="🛒 Add to Cart", style=discord.ButtonStyle.success, custom_id="persistent_addtocart", row=1)
    async def add_to_cart(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not interaction.message.attachments:
            await interaction.followup.send("⚠️ No product image found.", ephemeral=True)
            return

        file = interaction.message.attachments[0]
        parts = interaction.message.content.split(" - $")
        product_name = parts[0] if parts else "Unnamed Product"
        product_price = parts[1] if len(parts) > 1 else "Unknown"
        if not product_price.endswith("€"):
            product_price += "€"

        embed = discord.Embed(title=product_name, color=discord.Color.orange())
        embed.set_image(url=file.url)
        embed.add_field(name="💰 Price", value=product_price)

        user_id = interaction.user.id
        if user_id not in carts:
            carts[user_id] = []
        # Έλεγχος για διπλό προϊόν πριν την προσθήκη
        if any(existing_embed.title == embed.title for existing_embed in carts[user_id]):
            await interaction.followup.send("⚠️ This item is already in your cart.", ephemeral=True)
            return
    
        carts[user_id].append(embed)

        guild = interaction.guild
        existing_channel = discord.utils.get(guild.text_channels, name=f"cart-{interaction.user.name}")

        if not existing_channel or not existing_channel.permissions_for(interaction.guild.me).read_messages:
            carts[user_id] = [embed]
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True)
            }
            existing_channel = await guild.create_text_channel(
                name=f"cart-{interaction.user.name}",
                category=guild.get_channel(CART_CATEGORY_ID),
                overwrites=overwrites
            )

        await existing_channel.send(embed=embed, view=RemoveFromCartView(user_id=user_id, index=len(carts[user_id]) - 1))

        # Delete old summaries
        async for msg in existing_channel.history(limit=20):
            if msg.author == bot.user and msg.embeds:
                if msg.embeds[0].title == "🧾 Cart Summary":
                    await msg.delete()

        total = 0.0
        for embed in carts.get(user_id, []):
            for field in embed.fields:
                if field.name == "💰 Price":
                    price_text = field.value.replace("€", "").replace("$", "").strip()
                    try:
                        total += float(price_text)
                    except ValueError:
                        pass

        summary_embed = discord.Embed(
            title="🧾 Cart Summary",
            description=f"Total items: {len(carts[user_id])}",
            color=discord.Color.blue()
        )
        summary_embed.add_field(name="Total", value=f"{total:.2f}€")
        await existing_channel.send(embed=summary_embed, view=SummaryView(user_id=user_id))

        await interaction.followup.send("✅ Added to cart!", ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Submit Ticket", style=discord.ButtonStyle.primary, custom_id="persistent_ticket", row=0)
    async def submit_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild

        existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name}")
        if existing:
            await interaction.response.send_message("⚠️ You already have an open ticket.", ephemeral=True)
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True)
        }
        ticket_channel = await guild.create_text_channel(name=f"ticket-{interaction.user.name}",
                                                         category=guild.get_channel(TICKET_CATEGORY_ID),
                                                         overwrites=overwrites)
        await ticket_channel.send("A staff member will assist you shortly", view=CloseTicketView())
        await interaction.response.send_message("Ticket created!", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔄 Reopen Ticket", style=discord.ButtonStyle.success, custom_id="reopen_ticket")
    async def reopen_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Remove 'closed-' prefix if present
        channel_name = interaction.channel.name
        if channel_name.startswith("closed-"):
            new_name = channel_name[len("closed-"):]
        else:
            new_name = channel_name
        # Respond and edit channel
        await interaction.response.send_message("🔄 Ticket reopened.", ephemeral=True)
        await interaction.channel.edit(name=new_name, archived=False, locked=False)

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.secondary, custom_id="persistent___close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        log_channel = interaction.guild.get_channel(1365495903758323823)
        if log_channel:
            await log_channel.send(f"🗑️ Ticket `{interaction.channel.name}` marked for deletion in 3 hours.")
        # Inform user
        await interaction.response.send_message(
            "🔒 Ticket closed. You can reopen it within 3 hours.", ephemeral=True
        )
        # Rename channel to indicate closed status
        original_name = interaction.channel.name
        await interaction.channel.edit(name=f"closed-{original_name}")
        # Wait 3 hours before deletion
        await asyncio.sleep(10800)
        try:
            log_channel = interaction.guild.get_channel(1365495903758323823)
            if log_channel:
                await log_channel.send(f"🗑️ Ticket `{interaction.channel.name}` deleted after 3 hours.")
            await interaction.channel.delete()
        except Exception:
            pass

    @discord.ui.button(label="❌ Force Close Ticket", style=discord.ButtonStyle.danger, custom_id="persistent___force_close_ticket")
    async def force_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.guild_permissions.administrator:
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("You don’t have permission.", ephemeral=True)

class CartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        # Directly add the ConfirmPayView inside the cart summary
        for item in ConfirmPayView().children:
            self.add_item(item)


class ConfirmPayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="💳 Pay via PayPal",
            style=discord.ButtonStyle.link,
            url="https://www.paypal.me/deegraphicdesign"
        ))
        for item in UploadReceiptView().children:
            self.add_item(item)


class ProductModal(discord.ui.Modal, title="Post New Product"):
    forum_channel_id = discord.ui.TextInput(label="Forum Channel ID")
    name = discord.ui.TextInput(label="Product Name")
    price = discord.ui.TextInput(label="Price")

    async def on_submit(self, interaction: discord.Interaction):
        pending_products[interaction.user.id] = {
            "forum_channel_id": self.forum_channel_id.value,
            "name": self.name.value,
            "price": self.price.value,
            "channel_id": interaction.channel.id
        }
        await interaction.response.send_message("📷 Now send product images (with optional description) in this channel.", ephemeral=True)

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.author.bot:
        return

    if message.author.id not in pending_products:
        return

    data = pending_products.pop(message.author.id)

    if not message.attachments:
        await message.channel.send("⚠️ No image attached. Please try again.")
        return

    try:
        forum_channel = message.guild.get_channel(int(data["forum_channel_id"]))
        if not isinstance(forum_channel, discord.ForumChannel):
            raise ValueError("Not a forum channel")
    except Exception:
        await message.channel.send("❌ Invalid Forum Channel ID.")
        return

    file = await message.attachments[0].to_file()
    await forum_channel.create_thread(
        name=data["name"],
        content=f"{data['name']} - ${data['price']}",
        files=[file],
        view=AddToCartView()
    )
    await message.channel.send("✅ Product posted successfully!")

class PostProductView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Post New Product", style=discord.ButtonStyle.success, custom_id="persistent_postproduct", row=0)
    async def post_product(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.guild_permissions.administrator:
            await interaction.response.send_modal(ProductModal())
        else:
            await interaction.response.send_message("Admin only.", ephemeral=True)

# Remove From Cart View
class RemoveFromCartView(discord.ui.View):
    def __init__(self, user_id: int, index: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.index = index

    @discord.ui.button(label="❌ Remove from Cart", style=discord.ButtonStyle.danger, custom_id="persistent_remove_from_cart", row=0)
    async def remove_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This item is not in your cart.", ephemeral=True)
            return

        if self.user_id in carts and 0 <= self.index < len(carts[self.user_id]):
            carts[self.user_id].pop(self.index)
            await interaction.message.delete()

            cart_channel = interaction.channel
            total_price = 0
            for embed in carts[self.user_id]:
                for field in embed.fields:
                    if field.name == "💰 Price":
                        try:
                            total_price += float(field.value.replace('$', '').strip())
                        except ValueError:
                            pass

            async for msg in cart_channel.history(limit=20):
                if msg.author == bot.user and msg.embeds:
                    if msg.embeds[0].title == "🧾 Cart Summary":
                        await msg.delete()

            summary = discord.Embed(title="🧾 Cart Summary", description=f"Total items: {len(carts[self.user_id])}", color=discord.Color.blue())
            summary.add_field(name="Total Price", value=f"${total_price:.2f}")
            await cart_channel.send(embed=summary, view=CartView())

            await interaction.response.send_message("🗑️ Item removed from cart.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Couldn't remove item.", ephemeral=True)

# Functions (AddCart, Payment, Approve etc.)

import os
from datetime import datetime
ORDER_CSV_PATH = "orders.csv"

class CompleteOrderView(discord.ui.View):
    def __init__(self, user: discord.Member):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="📁 Files Sent", style=discord.ButtonStyle.primary, custom_id="persistent___files_sent")
    async def complete_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
            return

        await interaction.response.send_message("📦 Files have been sent to the user. Closing order...", ephemeral=True)
        await asyncio.sleep(2)
        try:
            log_channel = interaction.guild.get_channel(1365495903758323823)
            if log_channel:
                await log_channel.send(f"🗂️ Order channel `{interaction.channel.name}` deleted after files were sent.")
            await interaction.channel.delete()
        except Exception as e:
            print(f"Failed to delete order channel: {e}")

    @discord.ui.button(label="📤 Export to CSV", style=discord.ButtonStyle.secondary, custom_id="persistent___export_to_csv")
    async def export_csv(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
            return

        from datetime import timezone
        now = datetime.now(timezone.utc).strftime("%d/%m/%y %H:%M")
        row = [str(self.user.id), self.user.name, now, interaction.channel.name]
        file_exists = os.path.isfile(ORDER_CSV_PATH)

        with open(ORDER_CSV_PATH, "a", newline='', encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["User ID", "Username", "Date", "Channel", "Items", "Total"])
            items = []
            for embed in carts.get(self.user.id, []):
                items.append(f"{embed.title} - {next((f.value for f in embed.fields if f.name == '💰 Price'), 'N/A')}")
            row.append(" | ".join(items))
        total_price = 0.0
        for item in items:
            try:
                total_price += float(item.split(' - ')[1].replace('$', '').strip())
            except:
                pass
        row.append(f"${total_price:.2f}")
        writer.writerow(row)

        await interaction.response.send_message("✅ Order exported to CSV.", ephemeral=True)

        # Send to Google Sheets automatically
        try:
            import requests
            webhook_url = "https://script.google.com/macros/s/AKfycbzF82tgwTicwwncVtoBJ3P0SXxF2Oxo_CC2CRQcECABpU6bDyqKuUlO2epb4dIlzJA2-w/exec"
            total_price = 0.0
            for embed in carts.get(self.user.id, []):
                for field in embed.fields:
                    if field.name == "💰 Price":
                        try:
                            total_price += float(field.value.replace("$", "").strip())
                        except:
                            pass

            data = {
                "User ID": str(self.user.id),
                "Username": self.user.name,
                "Date": now,
                "Channel": interaction.channel.name,
                "Items": row[-1],
                "Total": f"${total_price:.2f}"
            }
            requests.post(webhook_url, json=data)
        except Exception as e:
            print(f"[Webhook Error] {e}")


class UploadReceiptView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📤 Upload Receipt", style=discord.ButtonStyle.primary, custom_id="persistent___upload_receipt")
    async def upload_receipt(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("📎 Please upload your receipt image or file.", ephemeral=True)

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and m.attachments

        try:
            msg = await bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Time expired. Please try again.", ephemeral=True)
            return

        receipt_channel = await interaction.guild.create_text_channel(
            name=f"receipt-{interaction.user.name}",
            category=interaction.guild.get_channel(RECEIPT_CATEGORY_ID),
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True)
            }
        )

        embed = discord.Embed(title="📥 New Receipt Submitted", color=discord.Color.orange())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_image(url=msg.attachments[0].url)
        embed.set_footer(text=f"User ID: {interaction.user.id}")

        await receipt_channel.send(content="<@&admin>", embed=embed, view=ApproveOrderView())
        await interaction.followup.send("✅ Receipt uploaded. Awaiting admin approval.", ephemeral=True)

class ApproveOrderView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🗑️ Delete Receipt", style=discord.ButtonStyle.danger, custom_id="persistent____delete_receipt")
    async def delete_receipt(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You don't have permission to delete this receipt.", ephemeral=True)
            return

        await interaction.response.send_message("🗑️ Receipt deleted.", ephemeral=True)
        await asyncio.sleep(1)
        try:
            await interaction.channel.delete()
        except Exception as e:
            print(f"Failed to delete receipt channel: {e}")

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.success, custom_id="persistent___approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You don't have permission to approve.", ephemeral=True)
            return

        user_id = int(interaction.message.embeds[0].footer.text.split(": ")[1])
        user = await interaction.guild.fetch_member(user_id)

        order_channel = await interaction.guild.create_text_channel(
            name=f"order-{user.name}",
            category=interaction.guild.get_channel(ORDERS_CATEGORY_ID),
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True)
            }
        )

        embed = discord.Embed(title="📦 Order Confirmed", description="Admin has approved the receipt.", color=discord.Color.green())
        embed.set_footer(text=f"User ID: {user.id}")

        await order_channel.send(embed=embed, view=CompleteOrderView(user))


        await interaction.response.send_message("🟢 Order approved and order channel created.", ephemeral=True)

        # Notify user's cart channel about receipt approval
        cart_channel = discord.utils.get(interaction.guild.text_channels, name=f"cart-{user.name}")
        if cart_channel:
            embed = discord.Embed(
                title="✅ Receipt Reviewed",
                description="Melisse has reviewed your receipt. Your files will be sent within 3 hours.",
                color=discord.Color.green()
            )
            await cart_channel.send(embed=embed, view=CloseCartView())



        # ✅ Prefix the order channel name to show completion
        await order_channel.edit(name=f"✅-{order_channel.name}")

        # ✅ Prefix the receipt channel name to show approval
        try:
            await interaction.channel.edit(name=f"✅-{interaction.channel.name}")
        except Exception as e:
            print(f"Failed to rename receipt channel: {e}")


        try:
            await asyncio.sleep(86400)  # 24 ώρες σε δευτερόλεπτα
            await order_channel.delete()
        except Exception as e:
            print(f"Failed to delete order channel: {e}")

        # Send confirmation to user's cart channel
        cart_channel = discord.utils.get(interaction.guild.text_channels, name=f"cart-{user.name}")
        if cart_channel:
            embed = discord.Embed(
                title="✅ Receipt Approved",
                description="Your payment has been approved. Final files will be sent to you via direct message.",
                color=discord.Color.green()
            )
            await cart_channel.send(embed=embed, view=CloseCartView())




        # ✅ Prefix the receipt channel name to show approval
        try:
            await interaction.channel.edit(name=f"✅-{interaction.channel.name}")
        except Exception as e:
            print(f"Failed to rename receipt channel: {e}")

class CloseCartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🛒 Close Cart", style=discord.ButtonStyle.success, custom_id="persistent_close_cart")
    async def close_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.guild_permissions.administrator:
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("❌ You don't have permission to close this order.", ephemeral=True)


# Slash Commands

@bot.tree.command(name="enable_google_export", description="📤 Export last order to Google Sheets")
@app_commands.checks.has_permissions(administrator=True)
async def enable_google_export(interaction: discord.Interaction):
    import requests
    if not os.path.exists(ORDER_CSV_PATH):
        await interaction.response.send_message("⚠️ No order data to export.", ephemeral=True)
        return

    webhook_url = "https://script.google.com/macros/s/AKfycbzF82tgwTicwwncVtoBJ3P0SXxF2Oxo_CC2CRQcECABpU6bDyqKuUlO2epb4dIlzJA2-w/exec"
    try:
        with open(ORDER_CSV_PATH, newline='', encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
            if not rows:
                await interaction.response.send_message("⚠️ No order data to export.", ephemeral=True)
                return
            latest = rows[-1]

        response = requests.post(webhook_url, json=latest)
        if response.status_code == 200:
            await interaction.response.send_message("✅ Order sent to Google Sheets.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Failed to send data. Status: {response.status_code}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="poll", description="🗳️ Create a poll with up to 5 custom options")
@app_commands.checks.has_permissions(administrator=True)
async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None, option5: str = None):
    options = [option1, option2, option3, option4, option5]
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    valid_options = [(emojis[i], opt) for i, opt in enumerate(options) if opt]

    if len(valid_options) < 2:
        await interaction.response.send_message("❌ You must provide at least two options.", ephemeral=True)
        return

    description = "\n".join([f"{emoji} {text}" for emoji, text in valid_options])
    embed = discord.Embed(title="🗳️ Poll", description=f"**{question}**\n\n{description}", color=discord.Color.teal())
    embed.set_footer(text=f"Poll by {interaction.user.display_name}")

    poll_message = await existing_channel.send(embed=embed)
    for emoji, _ in valid_options:
        await poll_message.add_reaction(emoji)

    await interaction.response.send_message("✅ Poll created.", ephemeral=True)

@bot.tree.command(name="server_stats", description="📈 View server-wide sales statistics")
@app_commands.checks.has_permissions(administrator=True)
async def server_stats(interaction: discord.Interaction):
    if not os.path.exists(ORDER_CSV_PATH):
        await interaction.response.send_message("⚠️ No orders have been exported yet.", ephemeral=True)
        return

    total_orders = 0
    total_revenue = 0.0
    total_items = 0
    product_counter = {}

    with open(ORDER_CSV_PATH, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_orders += 1
            items = row.get("Items", "").split(" | ") if "Items" in row else []
            total_items += len(items)
            for item in items:
                name, sep, price = item.partition(" - ")
                try:
                    total_revenue += float(price.replace("$", "").strip())
                except:
                    pass
                if name in product_counter:
                    product_counter[name] += 1
                else:
                    product_counter[name] = 1

    top_product = max(product_counter.items(), key=lambda x: x[1])[0] if product_counter else "N/A"

    embed = discord.Embed(title="📈 Server Sales Stats", color=discord.Color.gold())
    embed.add_field(name="🧾 Total Orders", value=str(total_orders))
    embed.add_field(name="📦 Total Items Sold", value=str(total_items))
    embed.add_field(name="💰 Total Revenue", value=f"${total_revenue:.2f}")
    embed.add_field(name="🔥 Top Product", value=top_product)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="user_stats", description="📊 View a specific user's purchase statistics")
@app_commands.checks.has_permissions(administrator=True)
async def user_stats(interaction: discord.Interaction, user: discord.User):
    user_id = str(user.id)
    total_orders = 0
    total_spent = 0.0
    total_items = 0
    products_counter = {}

    if not os.path.exists(ORDER_CSV_PATH):
        await interaction.response.send_message("⚠️ No orders have been recorded yet.", ephemeral=True)
        return

    with open(ORDER_CSV_PATH, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["User ID"] == user_id:
                total_orders += 1
                items = row.get("Items", "").split(" | ") if "Items" in row else []
                total_items += len(items)
                for item in items:
                    name, sep, price = item.partition(" - ")
                    try:
                        total_spent += float(price.replace("$", "").strip())
                    except:
                        pass
                    if name in products_counter:
                        products_counter[name] += 1
                    else:
                        products_counter[name] = 1

    most_common = max(products_counter.items(), key=lambda x: x[1])[0] if products_counter else "N/A"

    embed = discord.Embed(
        title=f"📊 Stats for {user.display_name}",
        color=discord.Color.purple()
    )
    embed.add_field(name="🛍 Total Orders", value=str(total_orders))
    embed.add_field(name="📦 Items Purchased", value=str(total_items))
    embed.add_field(name="💰 Total Spent", value=f"${total_spent:.2f}")
    embed.add_field(name="🔥 Most Purchased Product", value=most_common)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="download_orders")
@app_commands.checks.has_permissions(administrator=True)
async def download_orders(interaction: discord.Interaction):
    if not os.path.exists(ORDER_CSV_PATH):
        await interaction.response.send_message("⚠️ No orders have been exported yet.", ephemeral=True)
        return

    await interaction.response.send_message("📄 Here is the exported CSV & Excel:", ephemeral=True)
    await interaction.followup.send(file=discord.File(ORDER_CSV_PATH))

    # Convert CSV to Excel and send it as well
    try:
        import pandas as pd
        excel_path = ORDER_CSV_PATH.replace(".csv", ".xlsx")
        df = pd.read_csv(ORDER_CSV_PATH)
        if "Items" in df.columns:
            df["Total"] = df["Items"].apply(lambda x: f"${{sum(float(p.split(' - ')[1].replace('$','').strip()) for p in x.split(' | ') if ' - ' in p):.2f}}")
        df.to_excel(excel_path, index=False)
        await interaction.followup.send(file=discord.File(excel_path))
    except Exception as e:
        await interaction.followup.send(f"⚠️ Could not convert to Excel: {e}", ephemeral=True)

@bot.tree.command(name="setup_ticket_button")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket_button(interaction: discord.Interaction):
    await interaction.channel.send("🎟️ Open a ticket:", view=TicketView())
    await interaction.response.send_message("Ticket system set up.", ephemeral=True)

@bot.tree.command(name="setup_post_product")
@app_commands.checks.has_permissions(administrator=True)
async def setup_post_product(interaction: discord.Interaction):
    await interaction.channel.send("🛍️ Add a new product:", view=PostProductView())
    await interaction.response.send_message("Product system set up.", ephemeral=True)

@bot.tree.command(name="clear")
@app_commands.checks.has_permissions(administrator=True)
async def clear(interaction: discord.Interaction, amount: int = None):
    await interaction.response.defer(ephemeral=True)
    if amount:
        deleted = await interaction.channel.purge(limit=amount, check=lambda m: not m.pinned)
        msg = await interaction.followup.send(f"🧹 Deleted {len(deleted)} messages (excluding pinned).", ephemeral=True)
    else:
        deleted = await interaction.channel.purge(check=lambda m: not m.pinned)
        msg = await interaction.followup.send(f"🧹 Cleared {len(deleted)} messages (excluding pinned).", ephemeral=True)
    await asyncio.sleep(2)
    await msg.delete()

@bot.tree.command(name="force_sync", description="🔄 Force re-sync of slash commands")
@app_commands.checks.has_permissions(administrator=True)
async def force_sync(interaction: discord.Interaction):
    guild = discord.Object(id=1336017250813087877)
    synced = await bot.tree.sync(guild=guild)
    await interaction.response.send_message(f"✅ Synced {len(synced)} commands to this server.", ephemeral=True)

@bot.event
async def on_ready():
    await bot.wait_until_ready()
    guild = discord.Object(id=1336017250813087877)



    synced = await tree.sync()
    print(f"🌐 Synced {len(synced)} GLOBAL commands: {[cmd.name for cmd in synced]}")

    bot.add_view(UploadReceiptView())
    bot.add_view(ApproveOrderView())
    bot.add_view(TicketView())
    bot.add_view(PostProductView())
    bot.add_view(AddToCartView())
    bot.add_view(CloseCartView())

    print(f"✅ Logged in as {bot.user}")



class SummaryView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

        self.add_item(discord.ui.Button(
            label="💳 Pay via PayPal",
            style=discord.ButtonStyle.link,
            url="https://www.paypal.me/deegraphicdesign"
        ))

        # Include upload receipt button
        for item in UploadReceiptView().children:
            self.add_item(item)

        # Include close cart button
        self.add_item(CloseCartButton(user_id=user_id))

class CloseCartButton(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="🛑 Close Cart", style=discord.ButtonStyle.danger, custom_id="close_cart_button")
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Αυτό δεν είναι το δικό σου καλάθι.", ephemeral=True)
            return

        await interaction.channel.delete()
        
import os

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set")

bot.run(TOKEN)


