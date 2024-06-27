import boto3
from botocore.exceptions import ClientError
import json
from pandasql import sqldf
import pandas as pd


def getSecret():

    secret_name = "ufcDBcred"
    region_name = "us-west-1"

    #create client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e

    #format as dict before returning
    secret = get_secret_value_response['SecretString']
    return json.loads(secret)


def setupFeatures(fightsTable, fightersTable):


    """ 
    This query allows for us to see the win percentage of fighters throughout their careers
    """
    query = """ 
    SELECT fighterID, fighter, eventDate, eventID, fightID, AVG(winCount) OVER (PARTITION BY fighterID ORDER BY eventDate ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) as winPercentage
    FROM(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, winner, eventDate, eventID, fightID,
        CASE
            WHEN winner = fighterA THEN 1
            ELSE 0
        END as winCount
        FROM fightsTable 
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, winner, eventDate, eventID, fightID,
        CASE
            WHEN winner = fighterB THEN 1
            ELSE 0
        END as winCount
        FROM fightsTable
    ) as winCounts
    ORDER BY fighterID, eventDate
    """
    winPercentageResult = sqldf(query)

    """ 
    This table is dedicated to calculating the average fight time for a fighter throughout their ufc career
    """

    query = """
    SELECT fighter, fighterID, eventDate, eventID, fightID, AVG(`Minutes In Fight`) OVER (PARTITION BY fighterID ORDER BY eventDate ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) as `Average Fight Time`
    FROM(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fightsTable
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fightsTable
    ) innerQuery
    order by fighterID, eventDate
    """
    averageFightTimeResult = sqldf(query)

    """ 
    This block shows us the age of the fighter at the time of the bout
    """
    query = """
    select fighter, innerQuery.fighterID, DOB, eventID, fightID, 
        (julianday(innerQuery.eventDate) - julianday(DOB)) / 365.25 as Age
    from(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fightsTable
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fightsTable
    )innerQuery
    LEFT JOIN fightersTable on innerQuery.fighterID = fightersTable.fighterID
    """
    ageResult = sqldf(query)

    """ 
    This code block is dedicated towards finding the # of ufc fights (experience) a fighter had going into a bout
    """

    query = """ 
    select fighter, fighterID, eventDate, eventID, count(*) OVER (PARTITION BY fighterID ORDER BY eventDate ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) as `Number of Fights`
    from(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fightsTable
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, `Minutes In Fight`, eventDate, eventID, fightID
        FROM fightsTable
    ) innerQuery
    """
    experienceResult = sqldf(query)

    """ 
    This block is focused on finding the finish rate for fighters among their wins
    """

    query = """ 
    select fighter, fighterID, eventDate, eventID, fightID, AVG(numMethod) OVER (PARTITION BY fighterID ORDER BY eventDate ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) as `Finish Rate`
    FROM(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, eventDate, eventID, fightID,
        CASE
            WHEN method = 'KO/TKO' THEN 1
            WHEN method = 'Submission' THEN 1
            WHEN method = 'TKO - Doctor''s Stoppage' THEN 1
            ELSE 0
        END AS numMethod
        FROM fightsTable
        where winner = fighter
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, eventDate, eventID, fightID,
        CASE
            WHEN method = 'KO/TKO' THEN 1
            WHEN method = 'Submission' THEN 1
            WHEN method = 'TKO - Doctor''s Stoppage' THEN 1
            ELSE 0
        END AS numMethod
        FROM fightsTable
        where winner = fighter
    )
    """
    finishRateResult = sqldf(query)

    
    """ 
    This block is for calculating the striking differential
    """
    query = """ 
    SELECT fighter, fighterID, eventDate, eventID, fightID, significantStrikesLanded, significantStrikesAbsorbed
    FROM(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, fighter_A_sig_strikes as significantStrikesLanded, fighter_B_sig_strikes as significantStrikesAbsorbed, eventDate, eventID, fightID
        FROM fightsTable
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, fighter_B_sig_strikes as significantStrikesLanded, fighter_A_sig_strikes as significantStrikesAbsorbed, eventDate, eventID, fightID
        FROM fightsTable
    )
    """
    strikeDifferentialResult = sqldf(query)
    strikeDifferentialResult['significantStrikesLanded'] = strikeDifferentialResult['significantStrikesLanded'].astype(int)
    strikeDifferentialResult['significantStrikesAbsorbed'] = strikeDifferentialResult['significantStrikesAbsorbed'].astype(int)

    strikeDifferentialResult = strikeDifferentialResult.sort_values(by=['fighterID', 'eventDate'])
    strikeDifferentialResult['cumulativeStrikesLanded'] = strikeDifferentialResult.groupby('fighterID')['significantStrikesLanded'].cumsum().shift(1)
    strikeDifferentialResult['cumulativeStrikesAbsorbed'] = strikeDifferentialResult.groupby('fighterID')['significantStrikesAbsorbed'].cumsum().shift(1)

    # Calculate the strikeDifferential
    strikeDifferentialResult['strikeDifferential'] = strikeDifferentialResult['cumulativeStrikesLanded'] / strikeDifferentialResult['cumulativeStrikesAbsorbed']

    """ 
    This code block is dedicated to finding out the takedown differential
    """
    query = """ 
    SELECT fighter, fighterID, eventDate, eventID, takedownsLanded, takedownsAbsorbed, fightID
    FROM(
        SELECT fighterA as fighter, fighter_A_ID as fighterID, fighter_A_takedowns as takedownsLanded, fighter_B_takedowns as takedownsAbsorbed, eventDate, eventID, fightID
        FROM fightsTable
        UNION ALL
        SELECT fighterB as fighter, fighter_B_ID as fighterID, fighter_B_takedowns as takedownsLanded, fighter_A_takedowns as takedownsAbsorbed, eventDate, eventID, fightID
        FROM fightsTable
    )
    """
    takedownDifferentialResult = sqldf(query)

    takedownDifferentialResult = takedownDifferentialResult.sort_values(by=['fighterID', 'eventDate'])
    takedownDifferentialResult['takedownsLanded'] = takedownDifferentialResult['takedownsLanded'].astype(int)
    takedownDifferentialResult['takedownsAbsorbed'] = takedownDifferentialResult['takedownsAbsorbed'].astype(int)

    takedownDifferentialResult['cumulativeTakedownsLanded'] = takedownDifferentialResult.groupby('fighterID')['takedownsLanded'].cumsum().shift(1)
    takedownDifferentialResult['cumulativeTakedownsAbsorbed'] = takedownDifferentialResult.groupby('fighterID')['takedownsAbsorbed'].cumsum().shift(1)


    # Calculate the takedownDifferential
    takedownDifferentialResult['takedownDifferential'] = takedownDifferentialResult['cumulativeTakedownsLanded'] / takedownDifferentialResult['cumulativeTakedownsAbsorbed']

    """ 
    This block will extract the weight class and stance for each fighter
    """
    query = """ 
    SELECT fighterA as fighter, fighter_A_ID as fighterID, weightClass, fightersTable.stance, eventDate, eventID, fightID
    FROM fightsTable LEFT JOIN
    fightersTable on fightsTable.fighter_A_ID = fightersTable.fighterID
    UNION ALL
    SELECT fighterB as fighter, fighter_B_ID as fighterID, weightClass, fightersTable.stance, eventDate, eventID, fightID
    FROM fightsTable LEFT JOIN
    fightersTable on fightsTable.fighter_B_ID = fightersTable.fighterID
    """
    weightClassResult = sqldf(query)

    """ 
    This block will be focused on calculating the winstreak for fighters
    """
    query = """ 
    select *
    FROM(
    SELECT fighterA as fighter, fighterB as opponent, fighter_A_ID as fighterID, winner, eventDate, eventID, fightID,
    CASE
        WHEN fighterA = winner THEN 1
        ELSE 0
    end as winResult
    FROM fightsTable 
    UNION ALL
    SELECT fighterB as fighter, fighterA as oponnent, fighter_B_ID as fighterID, winner, eventDate, eventID, fightID,
    CASE
        WHEN fighterB = winner THEN 1
        ELSE 0
    end as winResult
    FROM fightsTable 
    )
    order by fighterID, eventDate
    """
    winstreakResult = sqldf(query)
    winstreakResult = createWinStreak(winstreakResult)

    """ 
    This code block is dedicated towards finding the fighters average control time
    """
    query = """ 
    SELECT fighterA as fighter, fighter_A_ID as fighterID, fighter_A_control_time as controlTime, `Minutes In Fight`, eventDate, eventID, fightID
    FROM fightsTable 
    UNION ALL
    SELECT fighterB as fighter, fighter_B_ID as fighterID, fighter_B_control_time as controlTime, `Minutes In Fight`, eventDate, eventID, fightID
    FROM fightsTable 
    """
    averageControlTimeResult = sqldf(query)

    averageControlTimeResult[['minutes', 'seconds']] = averageControlTimeResult['controlTime'].str.split(':', expand=True)
    averageControlTimeResult['minutes'] = averageControlTimeResult['minutes'].astype(int)
    averageControlTimeResult['seconds'] = averageControlTimeResult['seconds'].astype(int)
    averageControlTimeResult['Control Time In Minutes'] = averageControlTimeResult['minutes'] + averageControlTimeResult['seconds'] / 60
    averageControlTimeResult.drop(['minutes', 'seconds'], axis=1, inplace=True)
    averageControlTimeResult['Control Percentage'] = averageControlTimeResult['Control Time In Minutes'] / averageControlTimeResult['Minutes In Fight']

    query = """ 
    select *, AVG(`Control Percentage`) OVER (PARTITION BY fighterID ORDER BY eventDate ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) as `Average Control Time`
    from averageControlTimeResult
    """
    averageControlPercentageResult = sqldf(query)

    final = averageControlPercentageResult.loc[:, ['fighter', 'fighterID', 'Average Control Time', 'eventID', 'fightID']]
    testDF = joinTogether(final, 'final', experienceResult, 'experienceResult', 'Number of Fights')
    testDF = joinTogether(testDF, 'testDF', winPercentageResult, 'winPercentageResult', 'winPercentage')
    testDF = joinTogether(testDF,'testDF', averageFightTimeResult, 'averageFightTimeResult', 'Average Fight Time')
    testDF = joinTogether(testDF,'testDF', ageResult, 'ageResult', 'Age')
    testDF = joinTogether(testDF,'testDF', finishRateResult, 'finishRateResult', 'Finish Rate')
    testDF = joinTogether(testDF,'testDF', strikeDifferentialResult, 'strikeDifferentialResult', 'strikeDifferential')
    testDF = joinTogether(testDF,'testDF', takedownDifferentialResult, 'takedownDifferentialResult', 'takedownDifferential')
    testDF = joinTogether(testDF,'testDF', weightClassResult, 'weightClassResult', 'weightClass')
    testDF = joinTogether(testDF,'testDF', winstreakResult, 'winstreakResult', 'winStreak')
    testDF = joinTogether(testDF,'testDF', averageControlPercentageResult, 'averageControlPercentageResult', 'Control Percentage')

    testDF['row_number'] = testDF.groupby('fightID').cumcount() + 1

    # Define the SQL query to separate fighters and their stats
    query = """
    SELECT 
        fightID,
        MAX(CASE WHEN row_number = 1 THEN fighter ELSE NULL END) AS fighterA,
        MAX(CASE WHEN row_number = 2 THEN fighter ELSE NULL END) AS fighterB,
        MAX(CASE WHEN row_number = 1 THEN fighterID ELSE NULL END) AS fighterIDA,
        MAX(CASE WHEN row_number = 2 THEN fighterID ELSE NULL END) AS fighterIDB,
        MAX(CASE WHEN row_number = 1 THEN `Average Control Time` ELSE NULL END) AS averageControlTimeA,
        MAX(CASE WHEN row_number = 2 THEN `Average Control Time` ELSE NULL END) AS averageControlTimeB,
        MAX(CASE WHEN row_number = 1 THEN winPercentage ELSE NULL END) AS winPercentageA,
        MAX(CASE WHEN row_number = 2 THEN winPercentage ELSE NULL END) AS winPercentageB,
        MAX(CASE WHEN row_number = 1 THEN `Average Fight Time` ELSE NULL END) AS averageFightTimeA,
        MAX(CASE WHEN row_number = 2 THEN `Average Fight Time` ELSE NULL END) AS averageFightTimeB,
        MAX(CASE WHEN row_number = 1 THEN Age ELSE NULL END) AS ageA,
        MAX(CASE WHEN row_number = 2 THEN Age ELSE NULL END) AS ageB,
        MAX(CASE WHEN row_number = 1 THEN `Finish Rate` ELSE NULL END) AS finishRateA,
        MAX(CASE WHEN row_number = 2 THEN `Finish Rate` ELSE NULL END) AS finishRateB,
        MAX(CASE WHEN row_number = 1 THEN strikeDifferential ELSE NULL END) AS strikeDifferentialA,
        MAX(CASE WHEN row_number = 2 THEN strikeDifferential ELSE NULL END) AS strikeDifferentialB,
        MAX(CASE WHEN row_number = 1 THEN takedownDifferential ELSE NULL END) AS takedownDifferentialA,
        MAX(CASE WHEN row_number = 2 THEN takedownDifferential ELSE NULL END) AS takedownDifferentialB,
        MAX(CASE WHEN row_number = 1 THEN weightClass ELSE NULL END) AS weightClassA,
        MAX(CASE WHEN row_number = 2 THEN weightClass ELSE NULL END) AS weightClassB,
        MAX(CASE WHEN row_number = 1 THEN winStreak ELSE NULL END) AS winStreakA,
        MAX(CASE WHEN row_number = 2 THEN winStreak ELSE NULL END) AS winStreakB,
        MAX(CASE WHEN row_number = 1 THEN `Control Percentage` ELSE NULL END) AS controlPercentageA,
        MAX(CASE WHEN row_number = 2 THEN `Control Percentage` ELSE NULL END) AS controlPercentageB,
        MAX(CASE WHEN row_number = 1 THEN `Number of Fights` ELSE NULL END) AS numberOfFightsA,
        MAX(CASE WHEN row_number = 2 THEN `Number of Fights` ELSE NULL END) AS numberOfFightsB,
        MAX(eventID) AS eventID
    FROM testDF
    GROUP BY fightID
    """

    # Execute the SQL query using pandasql
    result_df = sqldf(query)

    return result_df

def createWinStreak(df: pd.DataFrame) -> pd.DataFrame:

    currentFighter = df['fighter'][0]
    refreshStreak = 0
    for index, row in df.iterrows():

        #handle first row
        if index == 0:
            df.loc[index, 'winStreak'] = refreshStreak
            continue

        #if we hit a new fighter auto insert 0 as the winstreak, update, and move on
        if currentFighter != row['fighter']:
            currentFighter = row['fighter']
            df.loc[index, 'winStreak'] = refreshStreak
            continue

        #catch when fighter lost their last fight, can insert 0 and move on
        if df.loc[(index-1), 'winner'] != df.loc[(index-1), 'fighter']:
            df.loc[index, 'winStreak'] = refreshStreak
            continue
        
        #since we are here it means that we are still on the same fighter and they havent lost
        df.loc[index, 'winStreak'] = df.loc[(index-1), 'winStreak'] + 1

    return df

def joinTogether(orgDF, orgDFString, joiningDF, joiningDFString, specialColumn):
    # Enclose the specialColumn in backticks if it contains spaces or special characters
    specialColumn = f'`{specialColumn}`' if ' ' in specialColumn or not specialColumn.isidentifier() else specialColumn
    
    query = f""" 
    SELECT odf.*, jdf.{specialColumn}
    FROM {orgDFString} as odf LEFT JOIN
    {joiningDFString} as jdf ON odf.eventID = jdf.eventID
    AND odf.fighterID = jdf.fighterID
    """
    env = {orgDFString: orgDF, joiningDFString: joiningDF}
    return sqldf(query, env)

#might eventually add height and reach?