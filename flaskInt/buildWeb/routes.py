"""Maps all of the routes for our web page"""
from collections import namedtuple
from flask import render_template, request
from buildWeb.forms import RegisterForm
from buildWeb import app, cursor

@app.route("/")
@app.route("/home")
def home_page():
    """Takes users to our static home page"""
    return render_template("home.html", currentPage="home")


@app.route("/blog")
def blog_page():
    """takes users to our static blog page"""
    return render_template("blog.html", currentPage="blog")


@app.route("/feedback")
def contact_page():
    """takes users to our static contact page"""
    return render_template("contact.html", currentPage="contact")


@app.route("/stats")
def stats_page():
    """takes users to our stats page populated from the sql query"""
    page = request.args.get("page", 1, type=int)
    Fighter = namedtuple("Fighter", "fighter_id firstName lastName DOB")
    query = """
    select fighterID, firstName, lastName, DOB
    FROM fighterHyperlinks
    LIMIT %s OFFSET %s
    """
    cursor.execute(query, (25, 25 * (page - 1)))
    fighters = cursor.fetchall()
    fighters = [Fighter(*fighter) for fighter in fighters]

    return render_template(
        "stat.html", fighters=fighters, page=page, currentPage="stats"
    )


@app.route("/fighter/<int:fighter_id>")
def fighter_page(fighter_id):
    """takes users to the fighters page populated from the sql query"""
    FighterStats = namedtuple(
        "FighterStats",
        "fighterID firstName lastName hyperlink Height Weight Reach Stance DOB Strikes_Landed_Per_Minute Strike_Accuracy Strikes_Absorbed_Per_Minute Strike_Defense Takedown_Average Takedown_Accuracy Takedown_Defense Submission_Average",
    )
    query = """
    select *
    from fighterHyperlinks
    where fighterID = %s
    """
    cursor.execute(query, (fighter_id,))
    fighter_stats = cursor.fetchone()
    fighter_stats = FighterStats(*fighter_stats)

    return render_template(
        "fighterPage.html", fighter_stats=fighter_stats, fighter_id=fighter_id
    )


@app.route("/register")
def register_page():
    """takes the users to the static register page form"""
    form = RegisterForm()

    if form.validate_on_submit():
        print("")
    return render_template("register.html", form=form)
