# -*- coding: utf-8 -*-

from flask import Flask, render_template, request

from flask_socketio import SocketIO, emit



app = Flask(__name__)

app.config['SECRET_KEY'] = 'secret_key_for_love_letter'



# 初始化 SocketIO，允许跨域以防万一

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')



# --- 配置区 (保持不变) ---

CONFIG_BASIC = {

    "1 - 侍卫 (Guard)": 5, "2 - 牧师 (Priest)": 2, "3 - 男爵 (Baron)": 2,

    "4 - 侍女 (Handmaid)": 2, "5 - 王子 (Prince)": 2, "6 - 国王 (King)": 1,

    "7 - 伯爵夫人 (Countess)": 1, "8 - 公主 (Princess)": 1

}



CONFIG_EXTENSION = {

    "0 - 刺客 (Assassin)": 1, "1 - 侍卫 (Guard)": 8, "0 - 弄臣 (Jester)": 1,

    "2 - 牧师(Priest)": 2, "2 - 红衣主教 (Cardinal)": 2, "3 - 男爵 (Baron)": 2,

    "3 - 男爵夫人 (Baroness)": 2, "4 - 侍女 (Handmaid)": 2, "4 - 马屁精 (Sycophant)": 2,

    "5 - 王子 (Prince)": 2, "5 - 伯爵 (Count)": 2, "6 - 国王 (King)": 1,

    "6 - 警官 (Constable)": 1, "7 - 女伯爵 (Countess)": 1, "7 - 太后": 1,

    "8 - 公主 (Princess)": 1, "9 - 大主教 (Bishop)": 1

}



# 全局状态

current_mode = 'basic'

current_config = CONFIG_BASIC.copy()

game_state = {key: 0 for key in current_config.keys()}



def calculate_data():

    """计算并在后台打包数据，准备发给前端"""

    stats = []

    total_remaining = 0

    sorted_keys = sorted(current_config.keys())



    for card in sorted_keys:

        total = current_config[card]

        played = game_state.get(card, 0)

        remaining = max(0, total - played)

        total_remaining += remaining

        

        stats.append({

            "name": card,

            "total": total,

            "played": played,

            "remaining": remaining,

            "probability": 0

        })

    

    for item in stats:

        if total_remaining > 0:

            item['probability'] = round((item['remaining'] / total_remaining) * 100, 1)

        else:

            item['probability'] = 0.0

            

    return {

        'stats': stats,

        'total_remaining': total_remaining,

        'current_mode': current_mode,

        'mode_name': '基础版 (16张)' if current_mode == 'basic' else '拓展版 (32张)'

    }



def broadcast_update():

    """向所有连接的人广播最新数据"""

    data = calculate_data()

    # 渲染HTML片段发送给前端，这样前端JS写起来最简单

    html_content = render_template('card_list_fragment.html', stats=data['stats'])

    emit('update_game', {

        'html': html_content,

        'total': data['total_remaining'],

        'mode_name': data['mode_name'],

        'current_mode': data['current_mode']

    }, broadcast=True)



@app.route('/')

def index():

    # 首次加载页面

    data = calculate_data()

    return render_template('index.html', data=data)



# --- SocketIO 事件处理 ---



@socketio.on('connect')

def handle_connect():

    #有人连上来了，把当前状态发给他

    broadcast_update()



@socketio.on('switch_mode')

def handle_switch(mode):

    global current_mode, current_config, game_state

    if mode == 'extension':

        current_mode = 'extension'

        current_config = CONFIG_EXTENSION.copy()

    else:

        current_mode = 'basic'

        current_config = CONFIG_BASIC.copy()

    game_state = {key: 0 for key in current_config.keys()}

    broadcast_update()



@socketio.on('card_action')

def handle_card_action(payload):

    # payload 格式: {'action': 'add', 'card': 'name'}

    action = payload.get('action')

    card_name = payload.get('card')

    

    if action == 'add':

        if card_name in game_state and game_state[card_name] < current_config[card_name]:

            game_state[card_name] += 1

    elif action == 'remove':

        if card_name in game_state and game_state[card_name] > 0:

            game_state[card_name] -= 1

    

    broadcast_update()



@socketio.on('reset_game')

def handle_reset():

    global game_state

    for key in game_state:

        game_state[key] = 0

    broadcast_update()



if __name__ == '__main__':

    # 注意这里变成了 socketio.run

    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
