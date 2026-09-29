"""宠物繁殖基因 - 带8个bug"""
from dataclasses import dataclass, field
import random

@dataclass
class Pet:
    pid: str
    genes: dict
    growth_rate: float
    skills: list
    gender: str
    age: str = "adult"  # bug7: 无幼年期

class BreedingSystem:
    def __init__(self):
        self.pets: dict[str, Pet] = {}
        self.cooldown = {}  # bug5: 只看母方
        self.generation = 0

    def breed(self, mother_id, father_id):
        mom = self.pets[mother_id]
        dad = self.pets[father_id]
        # bug1: 直接平均
        child_genes = {}
        for k in mom.genes:
            child_genes[k] = (mom.genes[k] + dad.genes[k]) / 2
        # bug2: 固定变异率
        if random.random() < 0.01:
            child_genes["mutant"] = True
        # bug3: 随机性别
        gender = random.choice(["male", "female"])
        # bug4: 随机继承技能
        skills = random.sample(mom.skills + dad.skills, min(2, len(mom.skills + dad.skills)))
        # bug6: 简单平均成长率
        growth = (mom.growth_rate + dad.growth_rate) / 2
        child = Pet(f"p{self.generation}", child_genes, growth, skills, gender)
        self.generation += 1
        return child

    def can_breed(self, pet_id):
        # bug5: 公方无冷却
        return pet_id not in self.cooldown

    def grow_up(self, pet_id):
        # bug7: 无成长过程
        self.pets[pet_id].age = "adult"
