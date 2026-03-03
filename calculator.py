from typing import List, Optional

class BoardGameComponent:
    """
    桌游组件基类 (基础游戏和拓展包共用的属性)
    """
    def __init__(self, name: str, rating: float, complexity: float, duration: int):
        self.name = name
        self.rating = rating
        self.complexity = complexity
        self.duration = duration  # 如果是拓展包，这里指的是它额外增加的标称时长

class BaseGame(BoardGameComponent):
    """
    基础游戏类
    """
    def __init__(self, name: str, rating: float, complexity: float, duration: int, p_rep: float):
        super().__init__(name, rating, complexity, duration)
        self.p_rep = p_rep  # 表征理论人数 (Representative Player Count)

class Expansion(BoardGameComponent):
    """
    拓展包类
    """
    pass

class GameBundle:
    """
    游戏组合类 (用于计算挂载了拓展包后的最终动态数据)
    """
    def __init__(self, base_game: BaseGame, expansions: Optional[List[Expansion]] = None):
        self.base_game = base_game
        self.expansions = expansions or []

    @property
    def total_rating(self) -> float:
        """
        计算总评分：核心锚定加权 (w_base 默认设为 0.8)
        """
        if not self.expansions:
            return self.base_game.rating
        
        w_base = 0.8
        exp_count = len(self.expansions)
        avg_exp_rating = sum(exp.rating for exp in self.expansions) / exp_count
        
        return round(w_base * self.base_game.rating + (1 - w_base) * avg_exp_rating, 2)

    @property
    def total_complexity(self) -> float:
        """
        计算总复杂度：最高复杂度底线 + 认知负荷税 (gamma 默认设为 0.15)
        """
        if not self.expansions:
            return self.base_game.complexity
        
        gamma = 0.15
        exp_count = len(self.expansions)
        
        # 提取基础游戏和所有拓展包中的最高复杂度
        all_complexities = [self.base_game.complexity] + [exp.complexity for exp in self.expansions]
        max_complexity = max(all_complexities)
        
        return round(max_complexity + (gamma * exp_count), 2)

    @property
    def total_duration(self) -> float:
        """
        计算总时长：基础时长 + 边际时间衰减 (折算系数 0.5)
        """
        if not self.expansions:
            return self.base_game.duration
        
        decay_factor = 0.5
        extra_duration = sum(exp.duration * decay_factor for exp in self.expansions)
        
        return int(self.base_game.duration + extra_duration)

    @property
    def p_rep(self) -> float:
        """
        获取表征人数。拓展包通常不改变核心最佳人数体验，因此直接继承基础游戏。
        如果特定拓展包改变了人数（如扩充到5-6人），可以在此做额外判断。
        """
        return self.base_game.p_rep

# ==========================================
# 实际数据测试用例
# ==========================================
if __name__ == "__main__":
    # 1. 实例化基础游戏：《璀璨宝石》
    splendor_base = BaseGame(
        name="璀璨宝石 (Splendor)", 
        rating=7.4, 
        complexity=1.78, 
        duration=30, 
        p_rep=3.0
    )

    # 2. 实例化拓展包：《城市拓展》
    # 假设城市拓展单独评分为 7.6，复杂度为 2.1，标称额外增加 15 分钟游玩时间
    cities_exp = Expansion(
        name="城市拓展 (Cities of Splendor)", 
        rating=7.3, 
        complexity=2.16, 
        duration=30
    )

    # 3. 组装游戏：纯基础局 vs 带拓展局
    vanilla_game = GameBundle(base_game=splendor_base)
    full_game = GameBundle(base_game=splendor_base, expansions=[cities_exp])

    print("--- 纯基础版数据 ---")
    print(f"评分: {vanilla_game.total_rating}")
    print(f"复杂度: {vanilla_game.total_complexity}")
    print(f"时长: {vanilla_game.total_duration} 分钟\n")

    print("--- 加入拓展后的最终数据 ---")
    print(f"合并评分: {full_game.total_rating}")
    print(f"合并复杂度: {full_game.total_complexity}")
    print(f"合并时长: {full_game.total_duration} 分钟")