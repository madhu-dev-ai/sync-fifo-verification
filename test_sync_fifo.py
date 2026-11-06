import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

DEPTH = 8   # must match the DEPTH parameter in sync_fifo.sv


class FifoModel:
    """Perfect FIFO in Python. This is the 'expected' behaviour."""

    def __init__(self, depth):
        self.depth = depth
        self.q = []

    def count(self):
        return len(self.q)

    def full(self):
        return len(self.q) == self.depth

    def empty(self):
        return len(self.q) == 0

    def step(self, wr, data, rd):
        """One clock cycle. Uses the state from BEFORE the clock edge."""
        do_wr = wr and not self.full()
        do_rd = rd and not self.empty()
        if do_rd:
            self.q.pop(0)
        if do_wr:
            self.q.append(data)


async def tick(dut):
    """Wait one clock edge, then 1 ns so outputs have settled."""
    await RisingEdge(dut.clk)
    await Timer(1, "ns")


async def reset(dut):
    dut.rst_n.value = 0
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.wr_data.value = 0
    await tick(dut)
    await tick(dut)
    dut.rst_n.value = 1
    await tick(dut)


def check(dut, model):
    """Scoreboard: compare the real FIFO with the model."""
    assert int(dut.count.value) == model.count(), \
        f"count: DUT={int(dut.count.value)} model={model.count()}"
    assert int(dut.full.value) == int(model.full()), \
        f"full: DUT={int(dut.full.value)} model={int(model.full())}"
    assert int(dut.empty.value) == int(model.empty()), \
        f"empty: DUT={int(dut.empty.value)} model={int(model.empty())}"
    if not model.empty():
        assert int(dut.rd_data.value) == model.q[0], \
            f"rd_data: DUT={int(dut.rd_data.value)} model={model.q[0]}"


async def cycle(dut, model, wr=0, data=0, rd=0):
    """Drive one clock cycle, update the model, run the scoreboard."""
    dut.wr_en.value = wr
    dut.wr_data.value = data
    dut.rd_en.value = rd
    model.step(wr, data, rd)
    await tick(dut)
    check(dut, model)


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset(dut)
    model = FifoModel(DEPTH)
    check(dut, model)
    return model


@cocotb.test()
async def test_fill_and_drain(dut):
    """Fill to full, then drain to empty."""
    model = await setup(dut)

    for i in range(DEPTH):
        await cycle(dut, model, wr=1, data=10 + i)
    await cycle(dut, model)
    assert int(dut.full.value) == 1

    for _ in range(DEPTH):
        await cycle(dut, model, rd=1)
    await cycle(dut, model)
    assert int(dut.empty.value) == 1


@cocotb.test()
async def test_write_when_full(dut):
    """Extra writes into a full FIFO must be ignored."""
    model = await setup(dut)

    for i in range(DEPTH):
        await cycle(dut, model, wr=1, data=100 + i)

    # Try to write 5 more words. They must be dropped.
    for i in range(5):
        await cycle(dut, model, wr=1, data=200 + i)
    assert int(dut.count.value) == DEPTH

    # Drain. The scoreboard checks every word is the original one.
    for _ in range(DEPTH):
        await cycle(dut, model, rd=1)
    assert int(dut.empty.value) == 1


@cocotb.test()
async def test_read_when_empty(dut):
    """Reads from an empty FIFO must be ignored."""
    model = await setup(dut)

    for _ in range(5):
        await cycle(dut, model, rd=1)
    assert int(dut.count.value) == 0
    assert int(dut.empty.value) == 1

    # FIFO must still work normally afterwards
    await cycle(dut, model, wr=1, data=0x42)
    assert int(dut.count.value) == 1
    assert int(dut.rd_data.value) == 0x42


@cocotb.test()
async def test_simultaneous_read_write(dut):
    """Read and write in the same cycle, at half full, empty and full."""
    model = await setup(dut)

    # Case 1: empty. The write wins, the read is ignored.
    await cycle(dut, model, wr=1, data=1, rd=1)
    assert int(dut.count.value) == 1

    # Case 2: half full. Count must stay the same.
    for i in range(3):
        await cycle(dut, model, wr=1, data=10 + i)
    start = int(dut.count.value)
    for i in range(20):
        await cycle(dut, model, wr=1, data=50 + i, rd=1)
    assert int(dut.count.value) == start

    # Case 3: full. The read wins, the write is ignored.
    while not model.full():
        await cycle(dut, model, wr=1, data=99)
    await cycle(dut, model, wr=1, data=77, rd=1)
    assert int(dut.count.value) == DEPTH - 1


@cocotb.test()
async def test_wraparound(dut):
    """Push 4 x DEPTH words through so the pointers wrap many times."""
    model = await setup(dut)

    n = 0
    for _ in range(4):
        for _ in range(5):
            await cycle(dut, model, wr=1, data=n & 0xFF)
            n += 1
        for _ in range(5):
            await cycle(dut, model, rd=1)
    assert int(dut.empty.value) == 1


@cocotb.test()
async def test_constrained_random(dut):
    """3000 random cycles with changing read/write bias, fixed seed."""
    import random
    SEED = 1234
    rng = random.Random(SEED)
    dut._log.info(f"random seed = {SEED}")

    model = await setup(dut)

    # (write probability, read probability)
    modes = [(0.8, 0.2), (0.2, 0.8), (0.5, 0.5)]
    seen = {"full": 0, "empty": 0, "both": 0, "wr_full": 0, "rd_empty": 0}

    for i in range(3000):
        if i % 100 == 0:
            p_wr, p_rd = rng.choice(modes)
        wr = int(rng.random() < p_wr)
        rd = int(rng.random() < p_rd)
        data = rng.randint(0, 255)

        # Coverage: note which situations we reached
        if model.full():
            seen["full"] += 1
            if wr:
                seen["wr_full"] += 1
        if model.empty():
            seen["empty"] += 1
            if rd:
                seen["rd_empty"] += 1
        if wr and rd:
            seen["both"] += 1

        await cycle(dut, model, wr=wr, data=data, rd=rd)

    dut._log.info(f"coverage: {seen}")
    for name, hits in seen.items():
        assert hits > 0, f"random test never reached: {name}"
