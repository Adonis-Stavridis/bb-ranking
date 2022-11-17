import os
from typing import Tuple

from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.middleware.proxy_fix import ProxyFix

import ranking
from db_query import get_select_query_result, run_insert_query, fetch_one_query_result

app = Flask(__name__)
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)
app.secret_key = os.urandom(12).hex()


@app.route("/")
@app.route("/index")
def index():
    player_solo_elo_list = get_select_query_result(
        """
        SELECT p.name as name, s.mu as solo_elo
        FROM players p
        JOIN solo_ranking s
        ON s.player_id = p.id
        ORDER BY solo_elo DESC
        LIMIT 10
        """
    )

    player_team_elo_list = get_select_query_result(
        """
        SELECT p.name as name, t.mu as team_elo
        FROM players p
        JOIN team_ranking t
        ON t.player_id = p.id
        ORDER BY team_elo DESC
        LIMIT 10
        """
    )

    player_list = get_select_query_result(
        """
        SELECT name
        FROM players
        ORDER BY name ASC
        """
    )

    recent_solo_games = get_select_query_result(
        """
        SELECT p_blue.name as blue_name, p_red.name as red_name, blue_score, red_score, sg.created_timestamp 
        FROM solo_game sg
        JOIN players p_blue
        ON sg.blue = p_blue.id
        JOIN players p_red
        ON sg.red = p_red.id
        ORDER BY sg.created_timestamp DESC
        LIMIT 5
        """
    )

    recent_team_games = get_select_query_result(
        """
        SELECT p_blue1.name + p_blue2.name as blue_names, p_red1.name + p_red2.name as blue_names, blue_score, red_score, tg.created_timestamp 
        FROM team_game tg
        JOIN players p_blue1
        ON tg.blue_player1 = p_blue1.id
        JOIN players p_blue2
        ON tg.blue_player2 = p_blue2.id
        JOIN players p_red1
        ON tg.red_player1 = p_red1.id
        JOIN players p_red2
        ON tg.red_player2 = p_red2.id
        ORDER BY tg.created_timestamp DESC
        LIMIT 5
        """
    )

    return render_template(
        "index.html",
        player_solo_elo_list=player_solo_elo_list,
        player_team_elo_list=player_team_elo_list,
        player_list=player_list,
        recent_solo_games=recent_solo_games,
        recent_team_games=recent_team_games,
    )


@app.route("/add_player", methods=['GET', 'POST'])
def add_player():
    if request.method == 'POST':
        name = request.form['name']
        run_insert_query("INSERT INTO players(name) VALUES (?)", (name,))
        player_id = fetch_one_query_result("SELECT id FROM players WHERE name=?", (name,))
        rating = ranking.get_initial_rating()
        print(player_id[0])
        print(rating.mu)
        print(rating.sigma)
        run_insert_query("INSERT INTO solo_ranking(player_id, mu, sigma) VALUES (?, ?, ?)", (player_id[0], rating.mu, 8.3))
        run_insert_query("INSERT INTO team_ranking(player_id, mu, sigma) VALUES (?, ?, ?)", (player_id[0], rating.mu, 8.3))
        flash('User Added', 'success')
        return redirect(url_for("index"))
    return render_template("add_player.html")


@app.route("/register_solo_game", methods=['GET', 'POST'])
def register_solo_game():
    if request.method == 'POST':
        print(f"GOT {request.form}")
        return add_solo_game_result(request)

    player_list = get_select_query_result("SELECT id, name FROM players")
    return render_template("register_solo_game.html", player_list=player_list)


def add_solo_game_result(request):
    blue = int(request.form['blue'])
    red = int(request.form['red'])
    blue_score = int(request.form['blue_score'])
    red_score = int(request.form['red_score'])
    went_under = "went_under" in request.form and request.form['went_under'] == "on"

    if not _validate_solo_game_parameters(blue, red, blue_score, red_score):
        return redirect(request.url)

    winner = blue if blue_score > red_score else red
    loser = blue if winner == red else red

    ranking.update_solo_ranking(winner, loser)

    run_insert_query(
        """INSERT INTO solo_game(blue, red, blue_score, red_score, went_under) VALUES (?,?,?,?,?)""",
        (blue, red, blue_score, red_score, went_under)
    )
    flash('Game Added', 'success')
    return redirect(url_for("index"))


def _validate_solo_game_parameters(blue, red, blue_score, red_score):
    """
    Return True if game is valid
    """
    if blue == red:
        flash("You can't play against yourself, dumbass")
        return False
    if blue_score == red_score:
        flash("Ties are not allowed, keep playing")
        return False
    return True


@app.route("/register_team_game", methods=['GET', 'POST'])
def register_team_game():
    if request.method == 'POST':
        print(f"GOT {request.form}")
        return add_team_game_result(request)

    player_list = get_select_query_result("SELECT id, name FROM players")
    return render_template("register_team_game.html", player_list=player_list)


def add_team_game_result(request):
    blue_team = (int(request.form['blue_player1']), int(request.form['blue_player2']))
    red_team = (int(request.form['red_player1']), int(request.form['red_player2']))
    blue_score = int(request.form['blue_score'])
    red_score = int(request.form['red_score'])
    went_under = "went_under" in request.form and request.form['went_under'] == "on"

    _validate_team_game_parameters(
        red_team,
        blue_team,
        blue_score,
        red_score,
    )

    winner = blue_team if blue_score > red_score else red_team
    loser = blue_team if winner == red_team else red_team

    ranking.update_team_ranking(winner, loser)

    run_insert_query(
        """
        INSERT INTO team_game(
            blue_player1,
            blue_player2,
            red_player1,
            red_player2,
            blue_score,
            red_score,
            went_under
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (blue_team[0], blue_team[1], red_team[0], red_team[1], blue_score, red_score, went_under)
    )
    flash('Game Added', 'success')
    return redirect(url_for("index"))


def _validate_team_game_parameters(
    red_team: Tuple[int, int],
    blue_team: Tuple[int, int],
    blue_score: int,
    red_score: int,
):
    assert red_team[0] != red_team[1] != blue_team[0] != blue_team[1], "Players need to be distinct"
    assert blue_score != red_score, "Ties are not allowed"


if __name__ == '__main__':
    app.run(debug=True)
