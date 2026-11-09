import unittest
from auto_dino import decide_action


def bird(y, x=90):
    return dict(type='pterodactyl', y=y, x=x, width=46, levels=[100, 75, 50])


class BirdTests(unittest.TestCase):
    def decide(self, obstacles, **extra):
        state = dict(playing=True, jumping=False, ducking=False, speed=10,
                     x=0, width=44, obstacles=obstacles)
        state.update(extra)
        return decide_action(state, .12)

    def test_high_runs_middle_ducks_low_jumps(self):
        self.assertEqual(self.decide([bird(50)]), 'run')
        self.assertEqual(self.decide([bird(75)]), 'duck')
        self.assertEqual(self.decide([bird(100)]), 'jump')

    def test_duck_until_tail_clears(self):
        self.assertEqual(self.decide([bird(75, -40)], ducking=True), 'duck')
        self.assertEqual(self.decide([bird(75, -55)], ducking=True), 'run')

    def test_high_bird_does_not_hide_cactus(self):
        cactus = dict(type='cactusLarge', y=90, x=105, width=25)
        self.assertEqual(self.decide([bird(50, 30), cactus]), 'jump')

    def test_airborne_never_ducks(self):
        self.assertEqual(self.decide([bird(75)], jumping=True), 'wait')

    def test_distant_bird_does_not_duck(self):
        self.assertEqual(self.decide([bird(75, 500)]), 'run')


if __name__ == '__main__':
    unittest.main()
