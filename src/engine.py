"""宠物繁殖与基因系统。

- 显性/隐性/共显性基因，表现型由基因型决定
- 变异率受道具、父母品质、繁殖次数影响
- 性别有概率权重，可被道具影响
- 技能按稀有度与父母技能等级加权继承
- 双方均有繁殖冷却，并记录繁殖次数
- 成长率在父母均值基础上 ±10% 波动
- 后代出生为幼年期，需喂养/时间才能成年
- 近亲繁殖有缺陷概率，系统记录族谱
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import ClassVar

BASE_MUTATION_RATE = 0.01
GROWTH_FLUCTUATION = 0.10
BREED_COOLDOWN_TICKS = 3
FEEDS_TO_ADULT = 3
TICKS_TO_ADULT = 5
INBREEDING_GENERATIONS = 3
MAX_MUTATION_RATE = 0.5

RARITY_WEIGHT = {"common": 1, "rare": 2, "epic": 3, "legendary": 5}
QUALITY_MUTATION_BONUS = {
    "common": 0.0, "fine": 0.005, "rare": 0.01, "epic": 0.02, "legendary": 0.03,
}
ITEM_MUTATION_BONUS = {"mutation_elixir": 0.05, "lucky_charm": 0.02}
ITEM_GENDER_WEIGHT = {"female_potion": ("female", 0.8), "male_potion": ("male", 0.8)}
CODOMINANT_TRAITS = {"pattern", "spots"}
DEFECTS = ("weak_constitution", "frail", "sterile")
BREED_COUNT_MUTATION_BONUS = 0.005


def _alleles(genotype) -> list[str]:
    alleles = [c for c in str(genotype) if c.isalpha()]
    return alleles or ["a"]


def _combine(a1: str, a2: str) -> str:
    return "".join(sorted((a1, a2), key=lambda a: (a.islower(), a)))


def _mutate_allele(allele: str) -> str:
    return allele.lower() if allele.isupper() else allele.upper()


def phenotype(trait: str, genotype: str) -> str:
    """由基因型推导表现型：显性优先，共显性性状同时表现。"""
    alleles = _alleles(genotype)
    if len(set(alleles)) == 1:
        return alleles[0]
    if trait in CODOMINANT_TRAITS:
        return "".join(sorted(a.upper() for a in alleles))
    for allele in alleles:
        if allele.isupper():
            return allele
    return alleles[0].lower()


@dataclass
class Pet:
    pid: str
    genes: dict
    growth_rate: float
    skills: list
    gender: str
    age: str = "adult"
    quality: str = "common"
    defects: list = field(default_factory=list)
    fed: int = 0
    age_ticks: int = 0
    breed_count: int = 0

    _registry: ClassVar[dict] = {}

    def __post_init__(self):
        Pet._registry[self.pid] = self

    def phenotype(self, trait: str) -> str:
        return phenotype(trait, self.genes[trait])


class BreedingSystem:
    def __init__(self):
        self.pets: dict[str, Pet] = {}
        self.cooldown: dict[str, int] = {}  # 双方都有冷却：pid -> 剩余 tick
        self.pedigree: dict[str, tuple] = {}  # 族谱：pid -> (mother_id, father_id)
        self.generation = 0
        self.time = 0

    def _resolve(self, pid: str) -> Pet:
        pet = self.pets.get(pid) or Pet._registry.get(pid)
        if pet is None:
            raise KeyError(pid)
        return pet

    # ---- 繁殖 ----

    def breed(self, mother_id, father_id, items=None):
        items = list(items or [])
        mom = self._resolve(mother_id)
        dad = self._resolve(father_id)
        if mom.gender != "female":
            raise ValueError(f"{mother_id} 不是母方")
        if dad.gender != "male":
            raise ValueError(f"{father_id} 不是公方")
        if not self.can_breed(mother_id):
            raise RuntimeError(f"{mother_id} 繁殖冷却中或未成年")
        if not self.can_breed(father_id):
            raise RuntimeError(f"{father_id} 繁殖冷却中或未成年")

        child_genes = self._inherit_genes(mom, dad, items)
        gender = self._roll_gender(items)
        skills = self._inherit_skills(mom, dad)
        growth = self._roll_growth(mom, dad)
        defects = self._roll_defects(mother_id, father_id)

        child = Pet(
            pid=f"p{self.generation}",
            genes=child_genes,
            growth_rate=growth,
            skills=skills,
            gender=gender,
            age="juvenile",  # 后代出生为幼年期
            defects=defects,
        )
        if "weak_constitution" in defects:
            child.growth_rate *= 0.8
        self.generation += 1
        self.pets[child.pid] = child
        self.pedigree[child.pid] = (mother_id, father_id)
        for pid, pet in ((mother_id, mom), (father_id, dad)):
            self.cooldown[pid] = BREED_COOLDOWN_TICKS  # 公方同样进入冷却
            pet.breed_count += 1
        return child

    def can_breed(self, pet_id):
        if self.cooldown.get(pet_id, 0) > 0:
            return False
        pet = self.pets.get(pet_id) or Pet._registry.get(pet_id)
        if pet is None:
            return True
        if pet.age != "adult":
            return False
        if "sterile" in pet.defects:
            return False
        return True

    # ---- 基因 ----

    def mutation_rate(self, mom: Pet, dad: Pet, items=None) -> float:
        """变异率 = 基础1% + 父母品质 + 父母繁殖次数 + 道具加成。"""
        rate = BASE_MUTATION_RATE
        rate += QUALITY_MUTATION_BONUS.get(mom.quality, 0.0)
        rate += QUALITY_MUTATION_BONUS.get(dad.quality, 0.0)
        rate += BREED_COUNT_MUTATION_BONUS * (mom.breed_count + dad.breed_count)
        for item in items or []:
            rate += ITEM_MUTATION_BONUS.get(item, 0.0)
        return min(rate, MAX_MUTATION_RATE)

    def _inherit_genes(self, mom, dad, items):
        rate = self.mutation_rate(mom, dad, items)
        child = {}
        for trait in set(mom.genes) | set(dad.genes):
            mom_alleles = _alleles(mom.genes.get(trait, "aa"))
            dad_alleles = _alleles(dad.genes.get(trait, "aa"))
            a1, a2 = random.choice(mom_alleles), random.choice(dad_alleles)
            if random.random() < rate:
                if random.random() < 0.5:
                    a1 = _mutate_allele(a1)
                else:
                    a2 = _mutate_allele(a2)
            child[trait] = _combine(a1, a2)
        return child

    # ---- 性别 ----

    def gender_weights(self, items=None) -> dict:
        weights = {"male": 0.5, "female": 0.5}
        for item in items or []:
            if item in ITEM_GENDER_WEIGHT:
                gender, weight = ITEM_GENDER_WEIGHT[item]
                other = "female" if gender == "male" else "male"
                weights[gender] = max(weights[gender], weight)
                weights[other] = 1.0 - weights[gender]
        return weights

    def _roll_gender(self, items):
        weights = self.gender_weights(items)
        return random.choices(list(weights), weights=list(weights.values()))[0]

    # ---- 技能 ----

    @staticmethod
    def _normalize_skill(skill) -> dict:
        if isinstance(skill, dict):
            return {
                "name": skill.get("name", "unknown"),
                "rarity": skill.get("rarity", "common"),
                "level": skill.get("level", 1),
            }
        return {"name": str(skill), "rarity": "common", "level": 1}

    def _inherit_skills(self, mom, dad, count=2):
        """按 稀有度权重 x 技能等级 加权无放回抽取，同名取最高权重。"""
        best = {}
        for owner in (mom, dad):
            for raw in owner.skills:
                skill = self._normalize_skill(raw)
                weight = RARITY_WEIGHT.get(skill["rarity"], 1) * skill["level"]
                if skill["name"] not in best or weight > best[skill["name"]][0]:
                    best[skill["name"]] = (weight, skill)
        pool = list(best.values())
        chosen = []
        for _ in range(min(count, len(pool))):
            total = sum(w for w, _ in pool)
            roll = random.uniform(0, total)
            acc = 0.0
            for i, (weight, skill) in enumerate(pool):
                acc += weight
                if roll <= acc:
                    chosen.append(dict(skill))
                    pool.pop(i)
                    break
        return chosen

    # ---- 成长 ----

    def _roll_growth(self, mom, dad):
        mean = (mom.growth_rate + dad.growth_rate) / 2
        return mean * random.uniform(1 - GROWTH_FLUCTUATION, 1 + GROWTH_FLUCTUATION)

    def feed(self, pet_id):
        pet = self.pets[pet_id]
        pet.fed += 1
        return pet.fed

    def tick(self, n=1):
        for _ in range(n):
            self.time += 1
            for pid in list(self.cooldown):
                self.cooldown[pid] = max(0, self.cooldown[pid] - 1)
            for pet in self.pets.values():
                if pet.age == "juvenile":
                    pet.age_ticks += 1

    def grow_up(self, pet_id):
        """幼年期需喂饱或经历足够时间才能成年。"""
        pet = self.pets[pet_id]
        if pet.age == "adult":
            return True
        if pet.fed >= FEEDS_TO_ADULT or pet.age_ticks >= TICKS_TO_ADULT:
            pet.age = "adult"
            return True
        return False

    # ---- 族谱与近亲 ----

    def ancestors(self, pid, generations=INBREEDING_GENERATIONS) -> dict:
        """返回 {祖先pid: 距离代数}。"""
        result = {}
        frontier = [(pid, 0)]
        while frontier:
            current, depth = frontier.pop()
            if depth >= generations:
                continue
            parents = self.pedigree.get(current)
            if not parents:
                continue
            for parent in parents:
                if parent not in result or result[parent] > depth + 1:
                    result[parent] = depth + 1
                frontier.append((parent, depth + 1))
        return result

    def relatedness(self, id_a, id_b) -> float:
        """亲缘系数：共同祖先与直系血缘贡献 0.5^代数。"""
        anc_a = self.ancestors(id_a)
        anc_b = self.ancestors(id_b)
        score = sum(0.5 ** (anc_a[p] + anc_b[p]) for p in set(anc_a) & set(anc_b))
        if id_a in anc_b:
            score += 0.5 ** anc_b[id_a]
        if id_b in anc_a:
            score += 0.5 ** anc_a[id_b]
        return score

    def is_related(self, id_a, id_b) -> bool:
        return self.relatedness(id_a, id_b) > 0

    def _roll_defects(self, mother_id, father_id):
        related = self.relatedness(mother_id, father_id)
        if related <= 0:
            return []
        chance = min(0.75, 2 * related)
        if random.random() < chance:
            return [random.choice(DEFECTS)]
        return []
