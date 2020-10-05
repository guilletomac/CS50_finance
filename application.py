import os

from cs50 import SQL
from datetime import datetime
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    
    # Select symbol owned by user and its quantity
    portfolios = db.execute("SELECT shares, symbol FROM portfolio WHERE id = :id", id = session["user_id"])
    
    # Temporary variable to store absolute total (stocks' total value + cash)
    grand_total = 0
    
    # Update each symbol prices and total
    for portfolio in portfolios:
        symbol = portfolio["symbol"]
        shares = portfolio["shares"]
        stock = lookup(symbol)
        total_stock_price = shares * stock["price"]
        grand_total += total_stock_price
        db.execute("UPDATE portfolio SET price = :price WHERE id = :id AND symbol = :symbol",
                    price = usd(stock["price"]), id = session["user_id"], symbol = symbol)
    
    # Selec user's cash
    users_cash = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])
    
    # Add shares' cahs with user's cash
    grand_total += users_cash[0]["cash"]
    
    # Select portfolio table
    updated_portfolio = db.execute("SELECT * from portfolio WHERE id = :id", id = session["user_id"])
    
    # Print portfolio to index homepage
    return render_template("index.html", stocks = updated_portfolio, cash = usd(users_cash[0]["cash"]), grand_total = usd(grand_total))

@app.route("/buy", methods = ["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached via POST (redirected to quoted.html)
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))

        # Ensure stock name was submitted and valid
        if not stock or not request.form.get("symbol"):
            return apology("Please submit a valid stock name", code=400)

        # Ensure "shares" is a positive number
        shares = int(request.form.get("shares"))
        if shares < 1:
            return apology("Shares must be positive number", 400)

        # Access user's money from database
        money = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])

        # Ensure user has enough money to buy the requested shares
        if not money or money[0]["cash"] < stock["price"] * shares:
            return apology("Not enough money to buy requested shares", 400)

        # Update history
        now = datetime.now().strftime('%y-%m-%d %H:%M:%S')
        db.execute("INSERT INTO histories (symbol, shares, price, id, transacted) VALUES(:symbol, :shares, :price, :id, :transacted)",
                    symbol = stock["symbol"], shares =+ shares, price = stock["price"], id = session["user_id"], transacted = now)
        
        # Update user's money
        db.execute("UPDATE users SET cash = cash - :cash WHERE id = :id", cash = stock["price"] * shares, id = session["user_id"])
        
        # Select user shares of specified symbol
        user_shares = db.execute("SELECT shares FROM portfolio WHERE id = :id AND symbol = :symbol",
                                 id = session["user_id"], symbol = stock["symbol"])        
        
        # if user has no shares of that symbol, create new stock
        if not user_shares:
            user_shares = db.execute("INSERT INTO portfolio (name, symbol, shares, price, total, id) VALUES(:name, :symbol, :shares, :price, :total, :id)",
                                    name = stock["name"], symbol = stock["symbol"], shares = shares, price = stock["price"], total = usd(stock["price"] * shares), id = session["user_id"])
        
        # If the user has shares of that symbol, increment shares count
        else:
            shares_count = user_shares[0]["shares"] + shares
            db.execute("UPDATE portfolio SET shares = :shares WHERE symbol = :symbol AND id = :id",
                        shares = shares_count, symbol = stock["symbol"], id = session["user_id"])
        
        return redirect("/")

    # User accessed buy.html via get
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    
    histories = db.execute("SELECT * from histories WHERE id = :id", id = session["user_id"])
    
    return render_template("history.html", histories=histories)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached via POST (redirected to quoted.html)
    if request.method == "POST":
        search = lookup(request.form.get("symbol"))

        # Ensure stock name was submitted and valid
        if not search:
            return apology("Please submit a valid stock name", code=400)

        search["price"] = usd(search["price"])

        return render_template("quoted.html", stock=search)

    # User accessed quote.html via get
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting the register form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide password confirmation", 403)

        # Ensure both passwords match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match", 403)

        # Insert the new user into "users" table
        result = db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=request.form.get(
            "username"), hash=generate_password_hash(request.form.get("password")))

        # Ensure username is not already in database
        if not result:
            return apology("username already exists", 400)

        # Remember which user has logged in
        session["user_id"] = result

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    
    symbols = db.execute("SELECT symbol FROM portfolio WHERE id = :id", id = session["user_id"])

    # User reached via POST (redirected to index)
    if request.method == "POST":
        
        # Ensure stock name was submitted and valid 
        if not request.form.get("symbol"):
            return apology("No symbol was selected", 400)
            
        stock = lookup(request.form.get("symbol"))
        
        # Ensure the symbol is valid
        if not stock:
            return apology("invalid symbol", 400)
            
        # Ensure valid number of shares are entered
        shares = int(request.form.get("shares"))
        
        if shares < 0:
            return apology("Shares bust be a positive number", 400)
            
        # Select user's shares
        user_shares = db.execute("SELECT shares FROM portfolio WHERE id = :id AND symbol = :symbol",
                                id = session["user_id"], symbol = stock["symbol"])
                                
        # Check if user has enough shares to sell
        if not shares or user_shares[0]["shares"] < shares:
            return apology("Not enough shares specified to sell", 400)
            
        # Update history
        now = datetime.now().strftime('%y-%m-%d %H:%M:%S')
        db.execute("INSERT INTO histories (symbol, shares, price, id, transacted) VALUES(:symbol, :shares, :price, :id, :transacted)",
                    symbol = stock["symbol"], shares =- shares, price = stock["price"], id = session["user_id"], transacted = now)
        
        # Update user's cash
        db.execute("UPDATE users SET cash= cash + :cash WHERE id = :id", cash = stock["price"] * shares, id = session["user_id"])
        
        # Select user shares of specified symbol
        user_shares = db.execute("SELECT shares FROM portfolio WHERE id = :id AND symbol = :symbol",
                                id = session["user_id"], symbol = stock["symbol"])
                                
        # Decrement amount of shares from user's portfolio
        shares_count = user_shares[0]["shares"] - shares
        
        # If user has no shares left, delete it
        if shares_count == 0:
            user_shares = db.execute("DELETE FROM portfolio WHERE id = :id AND name = :name", name = stock["name"], id = session["user_id"])
        
        # If user still has shares, update the shares count
        else:
            db.execute("UPDATE portfolio SET shares = :shares WHERE symbol = :symbol AND id = :id",
                        shares = shares_count, symbol = stock["symbol"], id = session["user_id"])

        return redirect("/")
               
    else:
        return render_template("sell.html", symbols = symbols)
        
@app.route("/cash", methods=["GET", "POST"])
@login_required
def cash():
    """Add cash for the user"""
    if request.method == "POST":

        # Ensure user has specified cash to be added
        if not request.form.get("cash"):
            return apology("No cash was selected", 400)

        cash_to_add = request.form.get("cash")

        # Update user's cash
        db.execute("UPDATE users SET cash = cash + :added WHERE id = :id", added=cash_to_add, id=session["user_id"])

        # Redirect user to index page after they make a purchase
        return redirect("/")

    else:
        return render_template("cash.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)