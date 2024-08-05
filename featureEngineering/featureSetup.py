"""
This file stores the sql queries that are used to create the features that will be fed into our prediction models.
"""

import json
from typing import Dict
import boto3
from botocore.exceptions import ClientError
import pandas as pd
from pandasql import sqldf


def get_secret() -> Dict:
    """Used to retrieve mysql info from aws secrets manager"""

    secret_name = "ufcDBcred"
    region_name = "us-west-1"

    # create client
    session = boto3.session.Session(profile_name="tmpJose")
    client = session.client(service_name="secretsmanager", region_name=region_name)
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise e

    # format as dict before returning
    secret = get_secret_value_response["SecretString"]
    return json.loads(secret)


def set_up_features(fights_table, fighters_table):
    """This method allows for us to create all the features from our starting data"""

    # This query allows for us to see the win percentage of fighters throughout their careers
    query = """ 
    SELECT fighterID, fighter, eventDate, eventID, fightID, AVG(winCount) OVER (PARTITION BY fighterID ORDER BY eventDate ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) as winPercentage
    FROM(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, winner, eventDate, eventID, fightID,
        CASE
            WHEN winner = fighterA THEN 1
            ELSE 0
        END as winCount
        FROM fights_table 
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, winner, eventDate, eventID, fightID,
        CASE
            WHEN winner = fighterB THEN 1
            ELSE 0
        END as winCount
        FROM fights_table
    ) as winCounts
    ORDER BY fighterID, eventDate
    """
    win_percentage_result = sqldf(query)

    # This table is dedicated to calculating the average fight time for a fighter throughout their ufc career
    query = """
    SELECT fighter, fighterID, eventDate, eventID, fightID, AVG(`Minutes In Fight`) OVER (PARTITION BY fighterID ORDER BY eventDate ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) as averageFightTime
    FROM(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fights_table
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fights_table
    ) innerQuery
    order by fighterID, eventDate
    """
    average_fight_time_result = sqldf(query)

    # This block shows us the age of the fighter at the time of the bout
    query = """
    select fighter, innerQuery.fighterID, DOB, eventID, fightID, 
        (julianday(innerQuery.eventDate) - julianday(DOB)) / 365.25 as Age
    from(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fights_table
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fights_table
    )innerQuery
    LEFT JOIN fighters_table on innerQuery.fighterID = fighters_table.fighterID
    """
    age_result = sqldf(query)

    # This code block is dedicated towards finding the # of ufc fights (experience) a fighter had going into a bout
    query = """ 
    select fighter, fighterID, eventDate, eventID, count(*) OVER (PARTITION BY fighterID ORDER BY eventDate ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) as numOfFights
    from(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fights_table
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fights_table
    ) innerQuery
    """
    experience_result = sqldf(query)

    # This block is focused on finding the finish rate for fighters among their wins
    query = """ 
    SELECT fighter, fighterID, eventDate, eventID, fightID, COALESCE(AVG(numMethod) OVER (PARTITION BY fighterID ORDER BY eventDate ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) as finishRate
    FROM(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, eventDate, eventID, fightID,
        CASE
            WHEN method = 'KO/TKO' AND winner = fighterA THEN 1
            WHEN method = 'Submission' AND winner = fighterA THEN 1
            WHEN method = 'TKO - Doctor''s Stoppage' AND winner = fighterA THEN 1
            WHEN winner != fighterA THEN 0
            ELSE 0
        END AS numMethod
        FROM fights_table
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, eventDate, eventID, fightID,
        CASE
            WHEN method = 'KO/TKO' AND winner = fighterB THEN 1
            WHEN method = 'Submission' AND winner = fighterB THEN 1
            WHEN method = 'TKO - Doctor''s Stoppage' AND winner = fighterB THEN 1
            WHEN winner != fighterB THEN 0
            ELSE 0
        END AS numMethod
        FROM fights_table
    )
    """
    finish_rate_result = sqldf(query)

    # This block is for calculating the striking differential
    query = """ 
    SELECT fighter, fighterID, eventDate, eventID, fightID, significantStrikesLanded, significantStrikesAbsorbed
    FROM(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, fighter_A_sig_strikes as significantStrikesLanded, fighter_B_sig_strikes as significantStrikesAbsorbed, eventDate, eventID, fightID
        FROM fights_table
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, fighter_B_sig_strikes as significantStrikesLanded, fighter_A_sig_strikes as significantStrikesAbsorbed, eventDate, eventID, fightID
        FROM fights_table
    )
    """
    strike_differential_result = sqldf(query)
    strike_differential_result["significantStrikesLanded"] = strike_differential_result[
        "significantStrikesLanded"
    ].astype(int)
    strike_differential_result["significantStrikesAbsorbed"] = (
        strike_differential_result["significantStrikesAbsorbed"].astype(int)
    )

    strike_differential_result = strike_differential_result.sort_values(
        by=["fighterID", "eventDate"]
    )
    strike_differential_result["cumulativeStrikesLanded"] = (
        strike_differential_result.groupby("fighterID")["significantStrikesLanded"]
        .cumsum()
        .shift(1)
    )
    strike_differential_result["cumulativeStrikesAbsorbed"] = (
        strike_differential_result.groupby("fighterID")["significantStrikesAbsorbed"]
        .cumsum()
        .shift(1)
    )

    # Calculate the strikeDifferential
    strike_differential_result["strikeDifferential"] = (
        strike_differential_result["cumulativeStrikesLanded"]
        / strike_differential_result["cumulativeStrikesAbsorbed"]
    )

    # This code block is dedicated to finding out the takedown differential
    query = """ 
    SELECT fighter, fighterID, eventDate, eventID, takedownsLanded, takedownsAbsorbed, fightID
    FROM(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, fighter_A_takedowns as takedownsLanded, fighter_B_takedowns as takedownsAbsorbed, eventDate, eventID, fightID
        FROM fights_table
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, fighter_B_takedowns as takedownsLanded, fighter_A_takedowns as takedownsAbsorbed, eventDate, eventID, fightID
        FROM fights_table
    )
    """
    takedown_differential_result = sqldf(query)

    takedown_differential_result = takedown_differential_result.sort_values(
        by=["fighterID", "eventDate"]
    )
    takedown_differential_result["takedownsLanded"] = takedown_differential_result[
        "takedownsLanded"
    ].astype(int)
    takedown_differential_result["takedownsAbsorbed"] = takedown_differential_result[
        "takedownsAbsorbed"
    ].astype(int)

    takedown_differential_result["cumulativeTakedownsLanded"] = (
        takedown_differential_result.groupby("fighterID")["takedownsLanded"]
        .cumsum()
        .shift(1)
    )
    takedown_differential_result["cumulativeTakedownsAbsorbed"] = (
        takedown_differential_result.groupby("fighterID")["takedownsAbsorbed"]
        .cumsum()
        .shift(1)
    )

    # Calculate the takedownDifferential
    takedown_differential_result["takedownDifferential"] = (
        takedown_differential_result["cumulativeTakedownsLanded"]
        / takedown_differential_result["cumulativeTakedownsAbsorbed"]
    )

    # This block will extract the weight class and stance for each fighter
    query = """ 
    SELECT fighterA as fighter, fighter_A_ID as fighterID, weightClass, fighters_table.stance, eventDate, eventID, fightID
    FROM fights_table LEFT JOIN
    fighters_table on fights_table.fighter_A_ID = fighters_table.fighterID
    UNION ALL
    SELECT fighterB as fighter, fighter_B_ID as fighterID, weightClass, fighters_table.stance, eventDate, eventID, fightID
    FROM fights_table LEFT JOIN
    fighters_table on fights_table.fighter_B_ID = fighters_table.fighterID
    """
    weightclass_result = sqldf(query)

    # This block will be focused on calculating the winstreak for fighters
    query = """ 
    select *
    FROM(
    SELECT fighterA as fighter, fighterB as opponent, fighter_A_ID as fighterID, winner, eventDate, eventID, fightID,
    CASE
        WHEN fighterA = winner THEN 1
        ELSE 0
    end as winResult
    FROM fights_table 
    UNION ALL
    SELECT fighterB as fighter, fighterA as oponnent, fighter_B_ID as fighterID, winner, eventDate, eventID, fightID,
    CASE
        WHEN fighterB = winner THEN 1
        ELSE 0
    end as winResult
    FROM fights_table 
    )
    order by fighterID, eventDate
    """
    winstreak_result = sqldf(query)
    winstreak_result = create_win_streak(winstreak_result)

    # This code block is dedicated towards finding the fighters average control time
    query = """ 
    SELECT fighterA as fighter, fighter_A_ID as fighterID, fighter_A_control_time as controlTime, `Minutes In Fight`, eventDate, eventID, fightID
    FROM fights_table 
    UNION ALL
    SELECT fighterB as fighter, fighter_B_ID as fighterID, fighter_B_control_time as controlTime, `Minutes In Fight`, eventDate, eventID, fightID
    FROM fights_table 
    """
    average_control_time_result = sqldf(query)

    average_control_time_result[["minutes", "seconds"]] = average_control_time_result[
        "controlTime"
    ].str.split(":", expand=True)
    average_control_time_result["minutes"] = average_control_time_result[
        "minutes"
    ].astype(int)
    average_control_time_result["seconds"] = average_control_time_result[
        "seconds"
    ].astype(int)
    average_control_time_result["Control Time In Minutes"] = (
        average_control_time_result["minutes"]
        + average_control_time_result["seconds"] / 60
    )
    average_control_time_result.drop(["minutes", "seconds"], axis=1, inplace=True)
    average_control_time_result["controlPercentage"] = (
        average_control_time_result["Control Time In Minutes"]
        / average_control_time_result["Minutes In Fight"]
    )

    query = """ 
    select *, AVG(controlPercentage) OVER (PARTITION BY fighterID ORDER BY eventDate ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) as averageControlTime
    from average_control_time_result
    """
    average_control_percentage_result = sqldf(query)

    final = average_control_percentage_result.loc[
        :, ["fighter", "fighterID", "averageControlTime", "eventID", "fightID"]
    ]
    test_df = join_together(
        final, "final", experience_result, "experience_result", "numOfFights"
    )
    test_df = join_together(
        test_df,
        "test_df",
        win_percentage_result,
        "win_percentage_result",
        "winPercentage",
    )
    test_df = join_together(
        test_df,
        "test_df",
        average_fight_time_result,
        "average_fight_time_result",
        "averageFightTime",
    )
    test_df = join_together(test_df, "test_df", age_result, "age_result", "Age")
    test_df = join_together(
        test_df, "test_df", finish_rate_result, "finish_rate_result", "finishRate"
    )
    test_df = join_together(
        test_df,
        "test_df",
        strike_differential_result,
        "strike_differential_result",
        "strikeDifferential",
    )
    test_df = join_together(
        test_df,
        "test_df",
        takedown_differential_result,
        "takedown_differential_result",
        "takedownDifferential",
    )
    test_df = join_together(
        test_df, "test_df", weightclass_result, "weightclass_result", "weightClass"
    )
    test_df = join_together(
        test_df, "test_df", winstreak_result, "winstreak_result", "winStreak"
    )
    test_df = join_together(
        test_df,
        "test_df",
        average_control_percentage_result,
        "average_control_percentage_result",
        "controlPercentage",
    )

    test_df["row_number"] = test_df.groupby("fightID").cumcount() + 1

    # Define the SQL query to separate fighters and their stats
    query = """
    SELECT 
        fightID,
        MAX(CASE WHEN row_number = 1 THEN fighter ELSE NULL END) AS fighterA,
        MAX(CASE WHEN row_number = 2 THEN fighter ELSE NULL END) AS fighterB,
        MAX(CASE WHEN row_number = 1 THEN fighterID ELSE NULL END) AS fighterIDA,
        MAX(CASE WHEN row_number = 2 THEN fighterID ELSE NULL END) AS fighterIDB,
        MAX(CASE WHEN row_number = 1 THEN averageControlTime ELSE NULL END) AS averageControlTimeA,
        MAX(CASE WHEN row_number = 2 THEN averageControlTime ELSE NULL END) AS averageControlTimeB,
        MAX(CASE WHEN row_number = 1 THEN winPercentage ELSE NULL END) AS winPercentageA,
        MAX(CASE WHEN row_number = 2 THEN winPercentage ELSE NULL END) AS winPercentageB,
        MAX(CASE WHEN row_number = 1 THEN averageFightTime ELSE NULL END) AS averageFightTimeA,
        MAX(CASE WHEN row_number = 2 THEN averageFightTime ELSE NULL END) AS averageFightTimeB,
        MAX(CASE WHEN row_number = 1 THEN Age ELSE NULL END) AS ageA,
        MAX(CASE WHEN row_number = 2 THEN Age ELSE NULL END) AS ageB,
        MAX(CASE WHEN row_number = 1 THEN finishRate ELSE NULL END) AS finishRateA,
        MAX(CASE WHEN row_number = 2 THEN finishRate ELSE NULL END) AS finishRateB,
        MAX(CASE WHEN row_number = 1 THEN strikeDifferential ELSE NULL END) AS strikeDifferentialA,
        MAX(CASE WHEN row_number = 2 THEN strikeDifferential ELSE NULL END) AS strikeDifferentialB,
        MAX(CASE WHEN row_number = 1 THEN takedownDifferential ELSE NULL END) AS takedownDifferentialA,
        MAX(CASE WHEN row_number = 2 THEN takedownDifferential ELSE NULL END) AS takedownDifferentialB,
        MAX(CASE WHEN row_number = 1 THEN weightClass ELSE NULL END) AS weightClassA,
        MAX(CASE WHEN row_number = 2 THEN weightClass ELSE NULL END) AS weightClassB,
        MAX(CASE WHEN row_number = 1 THEN winStreak ELSE NULL END) AS winStreakA,
        MAX(CASE WHEN row_number = 2 THEN winStreak ELSE NULL END) AS winStreakB,
        MAX(CASE WHEN row_number = 1 THEN controlPercentage ELSE NULL END) AS controlPercentageA,
        MAX(CASE WHEN row_number = 2 THEN controlPercentage ELSE NULL END) AS controlPercentageB,
        MAX(CASE WHEN row_number = 1 THEN numOfFights ELSE NULL END) AS numberOfFightsA,
        MAX(CASE WHEN row_number = 2 THEN numOfFights ELSE NULL END) AS numberOfFightsB,
        MAX(eventID) AS eventID
    FROM test_df
    GROUP BY fightID
    """

    # Execute the SQL query using pandasql
    result_df = sqldf(query)

    # join the winners back into test
    result_df = result_df.merge(
        fights_table[["fightID", "winner"]], on="fightID", how="left"
    )

    return result_df


def create_win_streak(df) -> pd.DataFrame:
    """Allows for us to create the winstreak feature for the fighters"""

    current_fighter = df["fighter"][0]
    refresh_streak = 0
    for index, row in df.iterrows():

        # handle first row
        if index == 0:
            df.loc[index, "winStreak"] = refresh_streak
            continue

        # if we hit a new fighter auto insert 0 as the winstreak, update, and move on
        if current_fighter != row["fighter"]:
            current_fighter = row["fighter"]
            df.loc[index, "winStreak"] = refresh_streak
            continue

        # catch when fighter lost their last fight, can insert 0 and move on
        if df.loc[(index - 1), "winner"] != df.loc[(index - 1), "fighter"]:
            df.loc[index, "winStreak"] = refresh_streak
            continue

        # since we are here it means that we are still on the same fighter and they havent lost
        df.loc[index, "winStreak"] = df.loc[(index - 1), "winStreak"] + 1

    return df


def join_together(
    org_df, org_df_string, joining_df, joining_df_string, special_column
) -> pd.DataFrame:
    """Joins together the dfs we created on the common eventID"""

    query = f""" 
    SELECT odf.*, jdf.{special_column}
    FROM {org_df_string} as odf LEFT JOIN
    {joining_df_string} as jdf ON odf.eventID = jdf.eventID
    AND odf.fighterID = jdf.fighterID
    """
    env = {org_df_string: org_df, joining_df_string: joining_df}
    return sqldf(query, env)


# might eventually add height and reach?
