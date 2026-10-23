# -*- coding: utf-8 -*-
"""Fixture: one pretrained component, so G3b has an instrument to calibrate. Never executed by the tests."""


def load_backbone(net, state):
    net.load_state_dict(state)
    return net
