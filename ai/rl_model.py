import os
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
import gymnasium as gym
from gymnasium import spaces


class TradingEnv(gym.Env):
    """Custom environment for trading bot RL training."""

    def __init__(self, features_df, initial_balance=10000):
        super(TradingEnv, self).__init__()

        self.features_df = features_df.reset_index(drop=True)
        self.initial_balance = initial_balance
        self.current_step = 0
        self.balance = initial_balance
        self.position = 0  # 0: no position, 1: long, -1: short
        self.entry_price = 0

        # Action space: 0=hold, 1=buy, 2=sell
        self.action_space = spaces.Discrete(3)

        # Observation space: features + balance + position
        n_features = len(self.features_df.columns) - 1  # exclude target
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(n_features + 2,), dtype=np.float32
        )

    def reset(self):
        self.current_step = 0
        self.balance = self.initial_balance
        self.position = 0
        self.entry_price = 0
        return self._get_observation()

    def step(self, action):
        current_price = self.features_df.iloc[self.current_step]['close']
        reward = 0

        # Execute action
        if action == 1 and self.position == 0:  # Buy
            self.position = 1
            self.entry_price = current_price
        elif action == 2 and self.position == 0:  # Sell
            self.position = -1
            self.entry_price = current_price
        elif action == 0 and self.position != 0:  # Close position
            pnl = (current_price - self.entry_price) * self.position
            self.balance += pnl
            reward = pnl
            self.position = 0
            self.entry_price = 0

        # Small penalty for holding
        if self.position != 0:
            reward -= 0.01

        self.current_step += 1
        done = self.current_step >= len(self.features_df) - 1

        return self._get_observation(), reward, done, {}

    def _get_observation(self):
        if self.current_step >= len(self.features_df):
            return np.zeros(self.observation_space.shape)

        row = self.features_df.iloc[self.current_step]
        features = row.drop('target').values.astype(np.float32)
        obs = np.concatenate([
            features,
            [self.balance / self.initial_balance],  # normalized balance
            [self.position]  # position
        ])
        return obs


class RLModel:
    def __init__(self):
        self.model_path = "ai/rl_trading_model.zip"
        self.model = None
        self._load_or_create_model()

    def _load_or_create_model(self):
        if os.path.exists(self.model_path):
            try:
                self.model = PPO.load(self.model_path)
                print("--- RL MODELL BETÖLTVE ---")
            except Exception as e:
                print(f"RL modell betöltési hiba: {e}")
                self.model = None
        else:
            print("--- NINCS RL MODELL, KÉSŐBB KELL BETANÍTANI ---")

    def train(self, features_df, total_timesteps=10000):
        """Train the RL model on historical data."""
        env = TradingEnv(features_df)
        vec_env = DummyVecEnv([lambda: env])

        if self.model is None:
            self.model = PPO("MlpPolicy", vec_env, verbose=1)

        self.model.learn(total_timesteps=total_timesteps)
        self.model.save(self.model_path)
        print(f"RL modell mentve: {self.model_path}")

    def predict_action(self, observation):
        """Predict action from current observation."""
        if self.model is None:
            return 0  # Hold

        try:
            action, _ = self.model.predict(observation, deterministic=True)
            return int(action)
        except Exception as e:
            print(f"RL prediction error: {e}")
            return 0

    def get_confidence_score(self, observation):
        """Get confidence score for the prediction."""
        if self.model is None:
            return 0.0

        try:
            action, _ = self.model.predict(observation, deterministic=False)
            # Simple confidence based on action probability
            return 0.5  # Placeholder - could be improved with action probabilities
        except Exception:
            return 0.0