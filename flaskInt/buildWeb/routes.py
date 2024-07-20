from buildWeb import app
from buildWeb import cursor
from buildWeb.forms import registerForm
from flask import render_template, request
from collections import namedtuple


@app.route("/")
@app.route("/home")
def homePage():
    return render_template("home.html", currentPage="home")


@app.route("/blog")
def blogPage():
    return render_template("blog.html", currentPage="blog")


@app.route("/feedback")
def contactPage():
    return render_template("contact.html", currentPage="contact")


@app.route("/stats")
def statsPage():
    page = request.args.get("page", 1, type=int)
    Fighter = namedtuple("Fighter", "fighter_id firstName lastName DOB")
    query = f"""
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


@app.route("/fighter/<int:fighterID>")
def fighterPage(fighterID):
    FighterStats = namedtuple(
        "FighterStats",
        "fighterID firstName lastName hyperlink Height Weight Reach Stance DOB Strikes_Landed_Per_Minute Strike_Accuracy Strikes_Absorbed_Per_Minute Strike_Defense Takedown_Average Takedown_Accuracy Takedown_Defense Submission_Average",
    )
    query = f"""
    select *
    from fighterHyperlinks
    where fighterID = %s
    """
    cursor.execute(query, (fighterID,))
    fighterStats = cursor.fetchone()
    fighterStats = FighterStats(*fighterStats)

    return render_template(
        "fighterPage.html", fighterStats=fighterStats, fighterID=fighterID
    )


@app.route("/register")
def registerPage():
    form = registerForm()

    if form.validate_on_submit():
        print("")
    return render_template("register.html", form=form)
