from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from vietlott_engine.api.schemas import Max3DRequest
from vietlott_engine.core.exceptions import DataValidationError
from vietlott_engine.game_theory.max3d import PRODUCTS, Max3DBaoAnalysis, ProductSummary, analyse_bao, get_product, product_summary

router = APIRouter(prefix="/max3d", tags=["max3d"])


def _product(code: str):
    try:
        return get_product(code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[ProductSummary])
def products() -> list[ProductSummary]:
    return [product_summary(p) for p in PRODUCTS.values()]


@router.get("/{product}", response_model=ProductSummary)
def product(product: str) -> ProductSummary:
    return product_summary(_product(product))


@router.post("/{product}/analyse", response_model=Max3DBaoAnalysis)
async def analyse(product: str, body: Max3DRequest) -> Max3DBaoAnalysis:
    prod = _product(product)
    try:
        return await asyncio.to_thread(analyse_bao, prod, body.kind, body.numbers, body.sims, body.seed, body.stake_multiple)
    except ValueError as exc:
        raise DataValidationError(str(exc)) from exc
