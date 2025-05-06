from play_game import play_game
import random
import csv


def run_tournament(model_instances, n_games=5, tournament_mode="mixed"):
    """
    Run a tournament based on the specified mode.

    Parameters:
    - model_instances: List of models participating (including Stockfish).
    - n_games: Number of games to play between each pair of models.
    - tournament_mode: Either "mixed" for LLM vs. LLM + Stockfish, or "vs_stockfish" for LLMs only vs. Stockfish.
    """
    results = {}
    games_played = []  # To track the games played

    # Identify Stockfish from the list of models based on its name
    stockfish_model = next((model for model in model_instances if model.name.lower() == "stockfish"), None)
    if stockfish_model is None:
        raise ValueError("Stockfish model not found in model_instances list.")

    # Initialize results for each model
    for model in model_instances:
        results[model.name] = {
            'wins': 0,
            'losses': 0,
            'draws': 0,
            'rating': model.rating
        }

    # Configure matchups based on tournament mode
    matchups = []
    if tournament_mode == "mixed":
        # All LLMs play against each other and Stockfish
        for i in range(len(model_instances)):
            for j in range(i + 1, len(model_instances)):
                agent1 = model_instances[i]
                agent2 = model_instances[j]
                for game_num in range(n_games):
                    if game_num % 2 == 0:
                        matchups.append((agent1, agent2))
                    else:
                        matchups.append((agent2, agent1))

    elif tournament_mode == "vs_stockfish":
        # Each LLM only plays against Stockfish
        for model in model_instances:
            if model != stockfish_model:
                for _ in range(n_games):
                    matchups.append((model, stockfish_model))
                    matchups.append((stockfish_model, model))

    # Shuffle the matchups to randomize the order
    random.shuffle(matchups)

    # Play each matchup
    for idx, (agent_white, agent_black) in enumerate(matchups):
        print(f"Game {idx + 1} between {agent_white.name} (White) and {agent_black.name} (Black)")

        try:
            import mlflow
            with mlflow.start_run() as run:
                mlflow.dspy.autolog()
                experiment_id = run.info.experiment_id
                run_id = run.info.run_id        
                winner = play_game(agent_white, agent_black, tournament_mode, experiment_id, run_id)
        except Exception as e:
            print(f"Error playing game: {e}")
            continue

        # Record the game details
        game_record = {
            'game_number': idx + 1,
            'white': agent_white.name,
            'black': agent_black.name,
            'winner': winner,
            'white_rating': agent_white.rating,
            'black_rating': agent_black.rating
        }
        games_played.append(game_record)
        print(game_record)

        # Update results based on the winner
        if winner == agent_white.name:
            results[agent_white.name]['wins'] += 1
            results[agent_black.name]['losses'] += 1
        elif winner == agent_black.name:
            results[agent_black.name]['wins'] += 1
            results[agent_white.name]['losses'] += 1
        else:
            results[agent_white.name]['draws'] += 1
            results[agent_black.name]['draws'] += 1

        # Update ratings in the results
        results[agent_white.name]['rating'] = agent_white.rating
        results[agent_black.name]['rating'] = agent_black.rating

    print("\nFinal Results:")
    for model_name, stats in results.items():
        print(f"{model_name}: Wins={stats['wins']}, Losses={stats['losses']}, "
              f"Draws={stats['draws']}, Rating={stats['rating']:.2f}")

    # Save final results to a CSV file
    with open('tournament_results.csv', 'w', newline='') as csvfile:
        fieldnames = ['Model Name', 'Wins', 'Losses', 'Draws', 'Rating']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for model_name, stats in results.items():
            writer.writerow({
                'Model Name': model_name,
                'Wins': stats['wins'],
                'Losses': stats['losses'],
                'Draws': stats['draws'],
                'Rating': f"{stats['rating']:.2f}"
            })

    # Optionally return the list of games played
    return games_played
