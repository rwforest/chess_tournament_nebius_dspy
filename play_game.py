import csv
import chess
import chess.pgn
import time
import os
import random
from datetime import datetime

def play_game(agent_white, agent_black, tournament_mode, experiment_id, run_id):
    moves = []
    board = chess.Board()
    current_datetime = datetime.now()
    feedback_white = ""
    feedback_black = ""
    move_count = 0

    game = chess.pgn.Game()
    game.headers["Event"] = "LLM Tournament Match"
    game.headers["White"] = agent_white.name
    game.headers["Black"] = agent_black.name
    game.headers["ExperimentID"] = experiment_id
    game.headers["RunID"] = run_id    
    game.headers["Date"] = current_datetime.strftime("%Y-%m-%d")
    game.headers["Time"] = current_datetime.strftime("%H:%M:%S")    

    while not board.is_game_over():
        if board.turn:
            current_agent = agent_white
            feedback = feedback_white
        else:
            current_agent = agent_black
            feedback = feedback_black

        board_state = board.fen()
        legal_moves = ', '.join([board.san(move) for move in board.legal_moves])
        history = ', '.join(moves)

        # if makes more than 2 minutes to get next move stop game and consider LLM lost
        start_time = time.time()

        while True:
            current_time = time.time()

            if current_time - start_time > 120:
                # Convert legal_moves to a list to get the length
                legal_moves_list = list(board.legal_moves)

                # Pick a random index from the list
                index = random.randint(0, len(legal_moves_list) - 1)

                # Get the move in SAN format
                next_move_str = board.san(legal_moves_list[index])
            else:
                next_move_str = current_agent.get_next_move(board_state, legal_moves, history, feedback)

            try:
                move = board.parse_san(next_move_str)
                if move in board.legal_moves:
                    break
                else:
                    feedback = f"Illegal move: {next_move_str}. Legal moves are: {legal_moves}"
                    print(feedback)
                    time.sleep(1)
            except Exception as e:
                feedback = f"Failed to parse move '{next_move_str}': {e}"

        _ = current_agent.evaluate_move(board, move)
        board.push(move)
        moves.append(next_move_str)
        move_count += 1
        print(f"{current_agent.name} plays: {next_move_str}")
        print(board)
        print("\n")
        
        # Check for draw or stalemate conditions
        if board.can_claim_threefold_repetition():
            print("Draw by threefold repetition.")
            break
        if board.can_claim_fifty_moves():
            print("Draw by the fifty-move rule.")
            break
        if board.is_stalemate():
            print("Draw by stalemate.")
            break
        if board.is_insufficient_material():
            print("Draw due to insufficient material.")
            break
        if board.is_seventyfive_moves():
            print("Draw by the seventy-five-move rule.")
            break
        if move_count >= 100:
            print("Draw due to exceeding maximum number of moves.")
            break
        if board.is_game_over():
            break        

    if move_count == 1:
        game.add_variation(move)
    else:
        node = game
        for past_move in board.move_stack[:-1]:
            node = node.add_variation(past_move)

    # Determine the result and update ratings
    result = board.result()
    game.headers["Result"] = result

    if result == "1-0":
        winner = agent_white
        agent_white.update_elo(agent_black, "win", tournament_mode)
        agent_black.update_elo(agent_white, "loss", tournament_mode)
        draw = False
    elif result == "0-1":
        winner = agent_black
        agent_black.update_elo(agent_white, "win", tournament_mode)
        agent_white.update_elo(agent_black, "loss", tournament_mode)
        draw = False
    else:
        draw = True
        agent_white.update_elo(agent_black, "draw", tournament_mode)
        agent_black.update_elo(agent_white, "draw", tournament_mode)

    file_exists = os.path.isfile("game_data.csv")

    # Log game result at the end for CSV
    print("writing to csv")
    with open("game_data.csv", "a", newline="") as csvfile:
        fieldnames = ["player", "cumulative_centipawn_loss", "blunders", "inaccuracies", "matches_top_n", "moves", "elo_rating"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        for agent in [agent_white, agent_black]:
            writer.writerow({
                "player": agent.name,
                "cumulative_centipawn_loss": agent.cumulative_centipawn_loss,
                "blunders": agent.blunder_count,
                "inaccuracies": agent.inaccuracy_count,
                "matches_top_n": agent.matching_moves_top_n,
                "moves": agent.total_moves,
                "elo_rating": agent.rating
            })

    with open("game.pgn", "a") as pgn_file:
        pgn_file.write(str(game) + '\n\n')

    # reinitialize the ratings for the next game, the idea is to see how
    # much drop or increase in the rating after each game on average
    agent_white.reset()
    agent_black.reset()

    if not draw:
        return winner.name

    return "Draw"
