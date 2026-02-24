import random

def get_player_choice():
    """プレイヤーの選択を受け取る"""
    while True:
        choice = input("あなたの選択を入力してください (グー, チョキ, パー): ").strip()
        if choice in ["グー", "チョキ", "パー"]:
            return choice
        else:
            print("無効な入力です。グー、チョキ、またはパーを入力してください。")

def get_computer_choice():
    """コンピュータのランダムな選択"""
    return random.choice(["グー", "チョキ", "パー"])

def determine_winner(player, computer):
    """勝敗を判定する"""
    if player == computer:
        return "引き分け"
    elif (player == "グー" and computer == "チョキ") or \
         (player == "チョキ" and computer == "パー") or \
         (player == "パー" and computer == "グー"):
        return "プレイヤーの勝ち"
    else:
        return "コンピュータの勝ち"

def play_game():
    """ゲームを実行する"""
    print("じゃんけんゲームを開始します！")
    
    while True:
        player_choice = get_player_choice()
        computer_choice = get_computer_choice()
        
        print(f"あなたの選択: {player_choice}")
        print(f"コンピュータの選択: {computer_choice}")
        
        result = determine_winner(player_choice, computer_choice)
        print(f"結果: {result}")
        
        # 続けるかどうか確認
        play_again = input("もう一度プレイしますか？(y/n): ").strip().lower()
        if play_again != 'y':
            print("ゲームを終了します。")
            break

if __name__ == "__main__":
    play_game()