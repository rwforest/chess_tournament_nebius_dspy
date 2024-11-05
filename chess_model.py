from openai import OpenAI
from dotenv import load_dotenv
import os
import chess
import chess.engine
import re
import dspy

load_dotenv()

PATH_TO_STOCKFISH = "/opt/homebrew/Cellar/stockfish/16/bin/stockfish"

engine = chess.engine.SimpleEngine.popen_uci(PATH_TO_STOCKFISH)


class ChessModel:
    def __init__(self, name, provider, model_id):
        self.name = name
        self.provider = provider
        self.model_id = model_id
        self.rating = 1500  # Initial Elo rating
        self.cumulative_centipawn_loss = 0
        self.blunder_count = 0
        self.inaccuracy_count = 0
        self.matching_moves_top_n = 0
        self.total_moves = 0

        if self.provider == 'nebius':
            self.client = OpenAI(
                base_url="https://api.studio.nebius.ai/v1/",
                api_key=os.environ.get("NEBIUS_API_KEY"),
            )
        elif self.provider == 'stockfish':
            self.client = chess.engine.SimpleEngine.popen_uci(PATH_TO_STOCKFISH)

    def reset(self):
        """Resets the model's statistics."""
        self.rating = 1500
        self.cumulative_centipawn_loss = 0
        self.blunder_count = 0
        self.inaccuracy_count = 0
        self.matching_moves_top_n = 0
        self.total_moves = 0

    def get_raw_response(self, board_state, legal_moves, history, feedback):
        if self.provider == 'stockfish':
            board = chess.Board(board_state)
            result = self.client.play(board, chess.engine.Limit(time=0.1))
            return result.move.uci()

        prompt = f"""
            You are a chess grandmaster. Given the current state of the chess board:
            {board_state}
            Legal moves: {legal_moves}
            History of moves so far: {history}
            Feedback on the previous move: {feedback}
            Generate the next move and explain your reasoning concisely.
            The move should be in a <move> tag
            """
        while True:
            if self.provider == 'openai':
                self.client = dspy.LM(f"openai/{self.model_id}")
                response = self.client(
                    messages=[{"role": "user", "content": f"{prompt}"}]
                )
                return response[0]

            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": f"{prompt}"}]
            )
            try:
                response.choices[0].message.content
                break
            except Exception as e:
                print(e)
                continue

        return response.choices[0].message.content

    @staticmethod
    def extract_move(response_content):
        """Extracts move in <move> tags."""
        pattern = re.compile(r'<move>(.*?)</move>', re.DOTALL)
        match = pattern.search(response_content)
        if match:
            return match.group(1).strip()
        return None

    def evaluate_move(self, board, llm_move, top_n=3):
        # if it is stockfish, we don't need to evaluate the move
        if self.provider == 'stockfish':
            return 0

        # Get Stockfish's top moves and evaluation scores
        # This get the top N moves stockfish would have played if it was the one playing
        result = engine.analyse(board, chess.engine.Limit(time=0.1), multipv=top_n)
        stockfish_top_moves = [info['pv'][0] for info in result]
        stockfish_best_score = result[0]['score'].relative.score()

        # Evaluate LLM's move
        board.push(llm_move)
        llm_result = engine.analyse(board, chess.engine.Limit(time=1.0))
        llm_score = llm_result['score'].relative.score()
        print(f"Stockfish: {stockfish_top_moves}, LLM: {llm_move}, Score: {llm_score}")
        board.pop()

        # Calculate centipawn loss
        try:
            centipawn_loss = abs(stockfish_best_score - llm_score)
        except TypeError:
            centipawn_loss = 0

        self.cumulative_centipawn_loss += centipawn_loss
        self.total_moves += 1

        print(f"Centipawn loss: {centipawn_loss}")

        # Count blunders and inaccuracies
        if centipawn_loss >= 100:
            self.blunder_count += 1
        elif 20 <= centipawn_loss < 100:
            self.inaccuracy_count += 1

        # Check if LLM's move is in Stockfish's top-N moves
        if llm_move in stockfish_top_moves:
            self.matching_moves_top_n += 1

        return centipawn_loss

    def get_next_move(self, board_state, legal_moves, history, feedback):
        unstructured_response = self.get_raw_response(board_state,
                                                      legal_moves,
                                                      history, feedback)

        if self.provider == 'stockfish':
            return unstructured_response

        move_text = self.extract_move(unstructured_response)

        return move_text

    def update_elo(self, opponent, game_result, tournament_mode, base_k=32):
        # Calculate expected outcome based on current ratings
        r_a = self.rating
        r_b = opponent.rating
        e_a = 1 / (1 + 10 ** ((r_b - r_a) / 400))

        # Determine score based on game result
        if game_result == "win":
            score = 1
        elif game_result == "loss":
            score = 0
        else:
            score = 0.5  # Draw

        # Adjust K-factor based on centipawn loss
        k_adj = base_k * self.cumulative_centipawn_loss / 1000

        # Update ratings based on adjusted K-factor
        self.rating += k_adj * (score - e_a)
        opponent.rating += k_adj * ((1 - score) - (1 - e_a))

        # Ensure ratings don’t drop below a minimum threshold
        self.rating = max(100, self.rating)
        opponent.rating = max(100, opponent.rating)

        print(f"{self.name} rating: {self.rating}, {opponent.name} rating: {opponent.rating}")
