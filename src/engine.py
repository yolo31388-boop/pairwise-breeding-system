"""宠物繁殖基因系统"""
from dataclasses import dataclass, field
import random
import time

# 全局宠物登记表：按 pid 索引所有已创建的宠物，
# 繁殖系统优先查自己的 pets，再回退到这里。
_REGISTRY: dict[str, "Pet"] = {}

# 性状遗传方式：dominant=显性/隐性，codominant=共显性
DEFAULT_MODE = "dominant"

# 技能稀有度权重，越稀有越优先遗传
RARITY_WEIGHT = {"common": 1.0, "rare": 2.0, "epic": 4.0, "legendary": 8.0}

# 道具效果
ITEM_EFFECTS = {
    "mutagen": {"mutation": 0.05},      # 变异剂：提高变异率
    "boy_potion": {"male": 0.3},        # 雄性药剂：提高生公概率
    "girl_potion": {"female": 0.3},     # 雌性药剂：提高生母概率
}

BASE_MUTATION_RATE = 0.01
MAX_MUTATION_RATE = 0.5
COOLDOWN_TICKS = 3          # 双方繁殖冷却（任意性别）
FEEDS_TO_ADULT = 3          # 幼年期需喂养次数
GROWTH_VARIANCE = 0.1       # 成长率 ±10% 波动
INBREED_DEFECT_CHANCE = 0.3
DEFECTS = ("frail", "weak", "sterile")


@dataclass
class Pet:
    pid: str
    genes: dict
    growth_rate: float
    skills: list
    gender: str
    age: str = "adult"
    quality: int = 1                 # 品质，影响变异率
    breed_count: int = 0             # 繁殖次数，影响变异率
    parents: tuple = ()              # 族谱：(母id, 父id)
    fed: int = 0                     # 幼年期喂养次数
    defects: list = field(default_factory=list)
    born_at: float = 0.0

    def __post_init__(self):
        _REGISTRY[self.pid] = self


def phenotype(genotype, mode=DEFAULT_MODE):
    """由基因型推导表现型。

    基因型为两个等位基因的字符串（如 "Aa"），大写为显性、小写为隐性。
    dominant: 至少一个显性等位基因则表现为显性，否则隐性。
    codominant: 杂合子表现为两者共显，纯合子表现为对应性状。
    """
    if not isinstance(genotype, str) or len(genotype) != 2:
        return genotype
    a, b = genotype
    if mode == "codominant" and a != b:
        return a + b
    dominant = [x for x in (a, b) if x.isupper()]
    if dominant:
        return dominant[0]
    return a


class BreedingSystem:
    def __init__(self):
        self.pets: dict[str, Pet] = {}
        self.cooldown: dict[str, int] = {}   # 双方都有冷却
        self.pedigree: dict[str, tuple] = {}  # 族谱：子代id -> (母id, 父id)
        self.trait_modes: dict[str, str] = {}  # 性状 -> dominant/codominant
        self.generation = 0

    # ---------- 查询 ----------

    def _resolve(self, ref):
        if isinstance(ref, Pet):
            return ref
        if ref in self.pets:
            return self.pets[ref]
        return _REGISTRY[ref]

    def can_breed(self, pet_id):
        pet = self._resolve(pet_id)
        if pet.age != "adult":
            return False
        return self.cooldown.get(pet_id, 0) <= 0

    def express(self, pet_id):
        """返回宠物各性状的表现型。"""
        pet = self._resolve(pet_id)
        return {
            trait: phenotype(g, self.trait_modes.get(trait, DEFAULT_MODE))
            for trait, g in pet.genes.items()
        }

    def _ancestors(self, pid, depth=5):
        """沿族谱向上收集祖先 id 集合。"""
        seen = set()
        stack = [(pid, depth)]
        while stack:
            cur, d = stack.pop()
            if d < 0:
                continue
            parents = self.pedigree.get(cur)
            if parents is None and cur in _REGISTRY:
                parents = _REGISTRY[cur].parents
            if not parents:
                continue
            for p in parents:
                if p not in seen:
                    seen.add(p)
                    stack.append((p, d - 1))
        return seen

    def is_inbred(self, mother_id, father_id):
        """双方有共同祖先（含一方是另一方祖先）即为近亲。"""
        mom_anc = self._ancestors(mother_id)
        dad_anc = self._ancestors(father_id)
        if mother_id in dad_anc or father_id in mom_anc:
            return True
        return bool(mom_anc & dad_anc)

    # ---------- 繁殖 ----------

    def mutation_rate(self, mom, dad, items=()):
        """基础1%，道具、父母品质、繁殖次数均可提升。"""
        rate = BASE_MUTATION_RATE
        rate += 0.01 * (mom.quality + dad.quality)
        rate += 0.005 * (mom.breed_count + dad.breed_count)
        for item in items:
            rate += ITEM_EFFECTS.get(item, {}).get("mutation", 0)
        return min(rate, MAX_MUTATION_RATE)

    def _roll_gender(self, items):
        weights = {"male": 0.5, "female": 0.5}
        for item in items:
            eff = ITEM_EFFECTS.get(item, {})
            for g in ("male", "female"):
                weights[g] += eff.get(g, 0)
        total = sum(weights.values())
        roll = random.random() * total
        for g, w in weights.items():
            roll -= w
            if roll <= 0:
                return g
        return "female"

    def _inherit_genes(self, mom, dad, mutate):
        """孟德尔遗传：父母各随机传一个等位基因，不做平均。"""
        child_genes = {}
        for trait in mom.genes:
            mg, dg = mom.genes[trait], dad.genes.get(trait)
            if isinstance(mg, str) and isinstance(dg, str) and len(mg) == 2 and len(dg) == 2:
                child_genes[trait] = random.choice(mg) + random.choice(dg)
            else:
                child_genes[trait] = random.choice([mg, dg])
        if mutate and child_genes:
            # 变异：随机翻转一个等位基因的显隐性
            trait = random.choice(list(child_genes))
            g = child_genes[trait]
            if isinstance(g, str) and len(g) == 2:
                i = random.randrange(2)
                flipped = g[i].swapcase()
                child_genes[trait] = g[:i] + flipped + g[i + 1:]
        if mutate:
            child_genes["mutant"] = True
        return child_genes

    def _inherit_skills(self, mom, dad, count=2):
        """按技能稀有度和父母技能等级加权继承。"""
        pool = {}
        for parent in (mom, dad):
            for skill in parent.skills:
                if isinstance(skill, dict):
                    name = skill.get("name")
                    rarity = skill.get("rarity", "common")
                    level = skill.get("level", 1)
                else:
                    name, rarity, level = skill, "common", 1
                weight = RARITY_WEIGHT.get(rarity, 1.0) * (1 + 0.2 * level)
                if weight > pool.get(name, (0,))[0]:
                    pool[name] = (weight, skill)
        names = list(pool)
        weights = [pool[n][0] for n in names]
        chosen = []
        for _ in range(min(count, len(names))):
            pick = random.choices(names, weights=weights, k=1)[0]
            i = names.index(pick)
            chosen.append(pool[pick][1])
            names.pop(i)
            weights.pop(i)
        return chosen

    def breed(self, mother_id, father_id, items=None):
        items = list(items or [])
        mom = self._resolve(mother_id)
        dad = self._resolve(father_id)
        if mom.gender != "female" or dad.gender != "male":
            raise ValueError("需要一雌一雄")
        if not self.can_breed(mom.pid) or not self.can_breed(dad.pid):
            raise ValueError("繁殖冷却中")

        mutate = random.random() < self.mutation_rate(mom, dad, items)
        child_genes = self._inherit_genes(mom, dad, mutate)
        gender = self._roll_gender(items)
        skills = self._inherit_skills(mom, dad)

        # 成长率：父母均值基础上 ±10% 波动
        growth = (mom.growth_rate + dad.growth_rate) / 2
        growth *= 1 + random.uniform(-GROWTH_VARIANCE, GROWTH_VARIANCE)

        child = Pet(
            pid=f"p{self.generation}",
            genes=child_genes,
            growth_rate=growth,
            skills=skills,
            gender=gender,
            age="baby",               # 后代为幼年期
            parents=(mom.pid, dad.pid),
            born_at=time.time(),
        )
        self.generation += 1

        # 近亲繁殖：缺陷概率
        if self.is_inbred(mom.pid, dad.pid) and random.random() < INBREED_DEFECT_CHANCE:
            child.defects.append(random.choice(DEFECTS))
            child.growth_rate *= 0.85

        # 记录族谱、冷却（双方）、繁殖次数
        self.pedigree[child.pid] = (mom.pid, dad.pid)
        self.cooldown[mom.pid] = COOLDOWN_TICKS
        self.cooldown[dad.pid] = COOLDOWN_TICKS
        mom.breed_count += 1
        dad.breed_count += 1
        self.pets[child.pid] = child
        return child

    # ---------- 成长 ----------

    def feed(self, pet_id):
        pet = self._resolve(pet_id)
        pet.fed += 1
        return pet.fed

    def grow_up(self, pet_id):
        """幼年期需喂养足够次数或经过足够时间才能成年。"""
        pet = self._resolve(pet_id)
        if pet.age == "adult":
            return True
        grown_by_time = pet.born_at and (time.time() - pet.born_at) >= 60
        if pet.fed >= FEEDS_TO_ADULT or grown_by_time:
            pet.age = "adult"
            return True
        return False

    def tick(self):
        """推进一个时间单位：双方冷却同步减少。"""
        for pid in list(self.cooldown):
            if self.cooldown[pid] > 0:
                self.cooldown[pid] -= 1
