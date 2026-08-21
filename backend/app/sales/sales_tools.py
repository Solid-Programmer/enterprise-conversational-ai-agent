"""Deterministic, read-only business analytics tools for AdventureWorks Sales.

The functions in this module deliberately use trusted SQL rather than generating
SQL from natural language.  They return only JSON-serializable dictionaries and
lists through :func:`app.db.sql_executor.execute_sql_query`.
"""

from typing import Any, Dict, List, Optional, Tuple

from app.db.sql_executor import execute_sql_query


def _header_filters(
    territory_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    salesperson_id: Optional[int] = None,
    country_region_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[str, Tuple[Any, ...]]:
    """Build parameterized predicates for a SalesOrderHeader alias named ``h``."""
    predicates: List[str] = []
    params: List[Any] = []
    if territory_id is not None:
        predicates.append("h.TerritoryID = ?")
        params.append(territory_id)
    if customer_id is not None:
        predicates.append("h.CustomerID = ?")
        params.append(customer_id)
    if salesperson_id is not None:
        predicates.append("h.SalesPersonID = ?")
        params.append(salesperson_id)
    if country_region_code is not None:
        predicates.append("t.CountryRegionCode = ?")
        params.append(country_region_code)
    if start_date is not None:
        predicates.append("h.OrderDate >= CAST(? AS date)")
        params.append(start_date)
    if end_date is not None:
        # OrderDate is datetime; this keeps the supplied end date inclusive.
        predicates.append("h.OrderDate < DATEADD(day, 1, CAST(? AS date))")
        params.append(end_date)
    return (" WHERE " + " AND ".join(predicates) if predicates else "", tuple(params))


def get_sales_performance(
    territory_id: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Return header-grain sales KPIs, monthly trend, and ranked territory results.

    Call for overall sales, a territory comparison, channel mix, or monthly sales
    trend.  ``territory_id`` and ISO dates are optional; absent dates mean all
    available order history.
    """
    where_sql, params = _header_filters(territory_id=territory_id, start_date=start_date, end_date=end_date)
    summary = execute_sql_query(f"""
        SELECT COALESCE(SUM(h.SubTotal), 0) AS revenue,
               COALESCE(SUM(h.TotalDue), 0) AS total_amount_due,
               COUNT(*) AS order_count, COUNT(DISTINCT h.CustomerID) AS distinct_customers,
               COALESCE(AVG(h.SubTotal), 0) AS avg_order_value,
               COALESCE(SUM(CASE WHEN h.OnlineOrderFlag = 1 THEN h.SubTotal ELSE 0 END), 0) AS online_revenue,
               COALESCE(SUM(CASE WHEN h.OnlineOrderFlag = 0 THEN h.SubTotal ELSE 0 END), 0) AS offline_revenue,
               SUM(CASE WHEN h.OnlineOrderFlag = 1 THEN 1 ELSE 0 END) AS online_order_count,
               SUM(CASE WHEN h.OnlineOrderFlag = 0 THEN 1 ELSE 0 END) AS offline_order_count,
               COALESCE(SUM(CASE WHEN h.OnlineOrderFlag = 1 THEN h.SubTotal ELSE 0 END) * 100.0
                        / NULLIF(SUM(h.SubTotal), 0), 0) AS online_revenue_pct
        FROM Sales.SalesOrderHeader AS h {where_sql};
    """, params)[0]
    monthly_trend = execute_sql_query(f"""
        WITH MonthlySales AS (
            SELECT DATEFROMPARTS(YEAR(h.OrderDate), MONTH(h.OrderDate), 1) AS month_start,
                   SUM(h.SubTotal) AS revenue, SUM(h.TotalDue) AS total_amount_due, COUNT(*) AS order_count
            FROM Sales.SalesOrderHeader AS h {where_sql}
            GROUP BY YEAR(h.OrderDate), MONTH(h.OrderDate)
        )
        SELECT month_start, revenue, total_amount_due, order_count,
               SUM(revenue) OVER (ORDER BY month_start ROWS UNBOUNDED PRECEDING) AS running_revenue,
               AVG(revenue) OVER (ORDER BY month_start ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS rolling_3_month_avg_revenue
        FROM MonthlySales ORDER BY month_start;
    """, params)
    territory_breakdown = execute_sql_query(f"""
        SELECT t.TerritoryID AS territory_id, t.Name AS territory_name, t.[Group] AS territory_group,
               SUM(h.SubTotal) AS revenue, SUM(h.TotalDue) AS total_amount_due, COUNT(*) AS order_count,
               COUNT(DISTINCT h.CustomerID) AS distinct_customers, AVG(h.SubTotal) AS avg_order_value,
               RANK() OVER (ORDER BY SUM(h.SubTotal) DESC) AS territory_rank
        FROM Sales.SalesOrderHeader AS h
        JOIN Sales.SalesTerritory AS t ON t.TerritoryID = h.TerritoryID
        {where_sql}
        GROUP BY t.TerritoryID, t.Name, t.[Group] ORDER BY territory_rank, territory_id;
    """, params)
    return {"filters": {"territory_id": territory_id, "start_date": start_date, "end_date": end_date},
            "summary": summary, "monthly_trend": monthly_trend, "territory_performance": territory_breakdown}


def get_customer_analysis(
    customer_id: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Return customer purchase behavior, rankings, reasons, and card-type use.

    Call with ``customer_id`` for one customer's detailed behavior; omit it for
    a ranked multi-customer summary. Store names are returned only for customers
    linked to ``Sales.Store``; no individual person names are inferred.
    """
    date_where, date_params = _header_filters(start_date=start_date, end_date=end_date)
    customer_predicate, customer_params = (" WHERE c.CustomerID = ?", (customer_id,)) if customer_id is not None else ("", ())
    customers = execute_sql_query(f"""
        WITH FilteredOrders AS (SELECT h.* FROM Sales.SalesOrderHeader AS h {date_where}),
        CustomerMetrics AS (
            SELECT c.CustomerID AS customer_id, c.StoreID AS store_id, s.Name AS store_name,
                   c.TerritoryID AS territory_id, c.AccountNumber AS account_number,
                   COUNT(fo.SalesOrderID) AS order_count, COALESCE(SUM(fo.SubTotal), 0) AS revenue,
                   COALESCE(SUM(fo.TotalDue), 0) AS total_amount_due, COALESCE(AVG(fo.SubTotal), 0) AS avg_order_value,
                   MIN(fo.OrderDate) AS first_order_date, MAX(fo.OrderDate) AS last_order_date,
                   COALESCE(SUM(CASE WHEN fo.OnlineOrderFlag = 1 THEN fo.SubTotal ELSE 0 END), 0) AS online_revenue,
                   COALESCE(SUM(CASE WHEN fo.OnlineOrderFlag = 0 THEN fo.SubTotal ELSE 0 END), 0) AS offline_revenue,
                   DATEDIFF(day, MIN(fo.OrderDate), MAX(fo.OrderDate)) * 1.0 / NULLIF(COUNT(fo.SalesOrderID) - 1, 0) AS avg_days_between_orders
            FROM Sales.Customer AS c
            LEFT JOIN Sales.Store AS s ON s.BusinessEntityID = c.StoreID
            LEFT JOIN FilteredOrders AS fo ON fo.CustomerID = c.CustomerID
            {customer_predicate}
            GROUP BY c.CustomerID, c.StoreID, s.Name, c.TerritoryID, c.AccountNumber
        )
        SELECT *, RANK() OVER (ORDER BY revenue DESC) AS customer_rank
        FROM CustomerMetrics
        {"" if customer_id is not None else "ORDER BY customer_rank, customer_id OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY"};
    """, date_params + customer_params)
    if customer_id is None:
        return {"filters": {"customer_id": None, "start_date": start_date, "end_date": end_date}, "customer_rankings": customers}

    header_where, header_params = _header_filters(customer_id=customer_id, start_date=start_date, end_date=end_date)
    purchase_reasons = execute_sql_query(f"""
        SELECT r.SalesReasonID AS reason_id, r.Name AS reason_name, r.ReasonType AS reason_type,
               COUNT(DISTINCT h.SalesOrderID) AS order_count
        FROM Sales.SalesOrderHeader AS h
        JOIN Sales.SalesOrderHeaderSalesReason AS hrs ON hrs.SalesOrderID = h.SalesOrderID
        JOIN Sales.SalesReason AS r ON r.SalesReasonID = hrs.SalesReasonID
        {header_where}
        GROUP BY r.SalesReasonID, r.Name, r.ReasonType ORDER BY order_count DESC, reason_id;
    """, header_params)
    payment_methods = execute_sql_query(f"""
        SELECT cc.CardType AS card_type, COUNT(*) AS order_count, SUM(h.TotalDue) AS total_amount_due
        FROM Sales.SalesOrderHeader AS h
        JOIN Sales.CreditCard AS cc ON cc.CreditCardID = h.CreditCardID
        {header_where}
        GROUP BY cc.CardType ORDER BY order_count DESC, card_type;
    """, header_params)
    return {"filters": {"customer_id": customer_id, "start_date": start_date, "end_date": end_date},
            "customer": customers[0] if customers else None, "purchase_reason_distribution": purchase_reasons,
            "payment_type_distribution": payment_methods}


def get_salesperson_performance(
    salesperson_id: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Return salesperson revenue, quota attainment, rankings, and territory history.

    Call for sales-representative comparisons or a specific representative's
    quota and territory performance. Orders and quota records are aggregated in
    separate CTEs before they are combined, preventing historical quotas from
    multiplying header revenue.
    """
    order_where, order_params = _header_filters(salesperson_id=salesperson_id, start_date=start_date, end_date=end_date)
    rep_filter, rep_params = (" WHERE p.BusinessEntityID = ?", (salesperson_id,)) if salesperson_id is not None else ("", ())
    quota_predicates, quota_params = [], []
    if salesperson_id is not None:
        quota_predicates.append("q.BusinessEntityID = ?"); quota_params.append(salesperson_id)
    if start_date is not None:
        quota_predicates.append("q.QuotaDate >= CAST(? AS date)"); quota_params.append(start_date)
    if end_date is not None:
        quota_predicates.append("q.QuotaDate < DATEADD(day, 1, CAST(? AS date))"); quota_params.append(end_date)
    quota_where = " WHERE " + " AND ".join(quota_predicates) if quota_predicates else ""
    performance = execute_sql_query(f"""
        WITH RepOrders AS (
            SELECT h.SalesPersonID, SUM(h.SubTotal) AS revenue, SUM(h.TotalDue) AS total_amount_due,
                   COUNT(*) AS order_count, AVG(h.SubTotal) AS avg_order_value
            FROM Sales.SalesOrderHeader AS h
            WHERE h.SalesPersonID IS NOT NULL {" AND " + order_where[7:] if order_where else ""}
            GROUP BY h.SalesPersonID
        ), PeriodQuota AS (
            SELECT q.BusinessEntityID, SUM(q.SalesQuota) AS period_quota, COUNT(*) AS quota_period_count
            FROM Sales.SalesPersonQuotaHistory AS q {quota_where}
            GROUP BY q.BusinessEntityID
        )
        SELECT p.BusinessEntityID AS salesperson_id, t.TerritoryID AS territory_id, t.Name AS territory_name,
               COALESCE(ro.revenue, 0) AS revenue, COALESCE(ro.total_amount_due, 0) AS total_amount_due,
               COALESCE(ro.order_count, 0) AS order_count, COALESCE(ro.avg_order_value, 0) AS avg_order_value,
               p.SalesQuota AS current_sales_quota, pq.period_quota, pq.quota_period_count,
               COALESCE(ro.revenue, 0) * 100.0 / NULLIF(pq.period_quota, 0) AS period_quota_attainment_pct,
               p.SalesYTD AS recorded_sales_ytd, p.SalesLastYear AS recorded_sales_last_year,
               RANK() OVER (ORDER BY COALESCE(ro.revenue, 0) DESC) AS salesperson_rank
        FROM Sales.SalesPerson AS p
        LEFT JOIN RepOrders AS ro ON ro.SalesPersonID = p.BusinessEntityID
        LEFT JOIN PeriodQuota AS pq ON pq.BusinessEntityID = p.BusinessEntityID
        LEFT JOIN Sales.SalesTerritory AS t ON t.TerritoryID = p.TerritoryID
        {rep_filter}
        ORDER BY salesperson_rank, salesperson_id;
    """, order_params + tuple(quota_params) + rep_params)
    monthly_sales = execute_sql_query(f"""
        WITH Monthly AS (
            SELECT h.SalesPersonID AS salesperson_id, DATEFROMPARTS(YEAR(h.OrderDate), MONTH(h.OrderDate), 1) AS month_start,
                   SUM(h.SubTotal) AS revenue, COUNT(*) AS order_count
            FROM Sales.SalesOrderHeader AS h
            WHERE h.SalesPersonID IS NOT NULL {" AND " + order_where[7:] if order_where else ""}
            GROUP BY h.SalesPersonID, YEAR(h.OrderDate), MONTH(h.OrderDate)
        )
        SELECT salesperson_id, month_start, revenue, order_count,
               AVG(revenue) OVER (PARTITION BY salesperson_id ORDER BY month_start ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS rolling_3_month_avg_revenue
        FROM Monthly ORDER BY salesperson_id, month_start;
    """, order_params)
    history_filter, history_params = (" WHERE th.BusinessEntityID = ?", (salesperson_id,)) if salesperson_id is not None else ("", ())
    territory_history = execute_sql_query(f"""
        SELECT th.BusinessEntityID AS salesperson_id, th.TerritoryID AS territory_id, t.Name AS territory_name,
               th.StartDate AS start_date, th.EndDate AS end_date, CASE WHEN th.EndDate IS NULL THEN 1 ELSE 0 END AS is_current_assignment
        FROM Sales.SalesTerritoryHistory AS th
        JOIN Sales.SalesTerritory AS t ON t.TerritoryID = th.TerritoryID
        {history_filter} ORDER BY salesperson_id, start_date;
    """, history_params)
    return {"filters": {"salesperson_id": salesperson_id, "start_date": start_date, "end_date": end_date},
            "salesperson_performance": performance, "monthly_sales": monthly_sales, "territory_history": territory_history}


def get_promotion_performance(
    special_offer_id: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Return special-offer effectiveness from correctly matched offer/product lines.

    Call to compare offers or investigate one ``special_offer_id``. The result
    labels default/no-discount offers explicitly; an offer ID alone is not
    treated as evidence of a discount.
    """
    predicates, params = [], []
    if special_offer_id is not None: predicates.append("d.SpecialOfferID = ?"); params.append(special_offer_id)
    if start_date is not None: predicates.append("h.OrderDate >= CAST(? AS date)"); params.append(start_date)
    if end_date is not None: predicates.append("h.OrderDate < DATEADD(day, 1, CAST(? AS date))"); params.append(end_date)
    where_sql = " WHERE " + " AND ".join(predicates) if predicates else ""
    offer_summary = execute_sql_query(f"""
        WITH OfferProductCounts AS (
            SELECT sop.SpecialOfferID, COUNT(DISTINCT sop.ProductID) AS associated_product_count
            FROM Sales.SpecialOfferProduct AS sop GROUP BY sop.SpecialOfferID
        ), OfferLines AS (
            SELECT d.SpecialOfferID, d.SalesOrderID, d.ProductID, d.OrderQty, d.LineTotal, d.UnitPriceDiscount, h.OrderDate
            FROM Sales.SalesOrderDetail AS d
            JOIN Sales.SpecialOfferProduct AS sop ON sop.SpecialOfferID = d.SpecialOfferID AND sop.ProductID = d.ProductID
            JOIN Sales.SalesOrderHeader AS h ON h.SalesOrderID = d.SalesOrderID {where_sql}
        ), OfferMetrics AS (
            SELECT SpecialOfferID, COUNT(DISTINCT SalesOrderID) AS distinct_orders, COUNT(DISTINCT ProductID) AS products_sold,
                   SUM(OrderQty) AS units_sold, SUM(LineTotal) AS line_revenue, AVG(UnitPriceDiscount) AS avg_discount_rate
            FROM OfferLines GROUP BY SpecialOfferID
        )
        SELECT o.SpecialOfferID AS special_offer_id, o.Description AS offer_description, o.Type AS offer_type, o.Category AS offer_category,
               o.DiscountPct AS offer_discount_pct, CASE WHEN o.DiscountPct = 0 THEN 1 ELSE 0 END AS is_default_or_no_discount_offer,
               o.StartDate AS offer_start_date, o.EndDate AS offer_end_date, opc.associated_product_count,
               om.distinct_orders, om.products_sold, om.units_sold, om.line_revenue, om.avg_discount_rate,
               RANK() OVER (ORDER BY om.line_revenue DESC) AS offer_rank
        FROM OfferMetrics AS om
        JOIN Sales.SpecialOffer AS o ON o.SpecialOfferID = om.SpecialOfferID
        LEFT JOIN OfferProductCounts AS opc ON opc.SpecialOfferID = o.SpecialOfferID
        ORDER BY offer_rank, special_offer_id;
    """, tuple(params))
    monthly_performance = execute_sql_query(f"""
        SELECT d.SpecialOfferID AS special_offer_id, DATEFROMPARTS(YEAR(h.OrderDate), MONTH(h.OrderDate), 1) AS month_start,
               COUNT(DISTINCT d.SalesOrderID) AS distinct_orders, SUM(d.OrderQty) AS units_sold, SUM(d.LineTotal) AS line_revenue
        FROM Sales.SalesOrderDetail AS d
        JOIN Sales.SpecialOfferProduct AS sop ON sop.SpecialOfferID = d.SpecialOfferID AND sop.ProductID = d.ProductID
        JOIN Sales.SalesOrderHeader AS h ON h.SalesOrderID = d.SalesOrderID {where_sql}
        GROUP BY d.SpecialOfferID, YEAR(h.OrderDate), MONTH(h.OrderDate)
        ORDER BY special_offer_id, month_start;
    """, tuple(params))
    return {"filters": {"special_offer_id": special_offer_id, "start_date": start_date, "end_date": end_date},
            "offer_performance": offer_summary, "monthly_performance": monthly_performance}


def get_currency_sales_analysis(
    country_region_code: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Return territory sales, local currency mappings, and recorded exchange-rate data.

    Call for country/territory sales and currency-rate questions. Recorded
    monetary values are not converted: rate direction is reported separately so
    this tool never assumes an unsupported conversion convention.
    """
    where_sql, params = _header_filters(country_region_code=country_region_code, start_date=start_date, end_date=end_date)
    territory_sales = execute_sql_query(f"""
        SELECT t.CountryRegionCode AS country_region_code, t.TerritoryID AS territory_id, t.Name AS territory_name, t.[Group] AS territory_group,
               SUM(h.SubTotal) AS revenue, SUM(h.TotalDue) AS total_amount_due, COUNT(*) AS order_count, AVG(h.SubTotal) AS avg_order_value,
               RANK() OVER (ORDER BY SUM(h.SubTotal) DESC) AS territory_rank
        FROM Sales.SalesOrderHeader AS h
        JOIN Sales.SalesTerritory AS t ON t.TerritoryID = h.TerritoryID {where_sql}
        GROUP BY t.CountryRegionCode, t.TerritoryID, t.Name, t.[Group] ORDER BY territory_rank, territory_id;
    """, params)
    currencies = execute_sql_query("""
        SELECT crc.CountryRegionCode AS country_region_code, crc.CurrencyCode AS currency_code, c.Name AS currency_name
        FROM Sales.CountryRegionCurrency AS crc
        JOIN Sales.Currency AS c ON c.CurrencyCode = crc.CurrencyCode
        WHERE (? IS NULL OR crc.CountryRegionCode = ?)
        ORDER BY country_region_code, currency_code;
    """, (country_region_code, country_region_code))
    monthly_sales = execute_sql_query(f"""
        WITH MonthlySales AS (
            SELECT t.CountryRegionCode AS country_region_code,
                   DATEFROMPARTS(YEAR(h.OrderDate), MONTH(h.OrderDate), 1) AS month_start,
                   SUM(h.SubTotal) AS revenue, COUNT(*) AS order_count
            FROM Sales.SalesOrderHeader AS h
            JOIN Sales.SalesTerritory AS t ON t.TerritoryID = h.TerritoryID {where_sql}
            GROUP BY t.CountryRegionCode, YEAR(h.OrderDate), MONTH(h.OrderDate)
        )
        SELECT country_region_code, month_start, revenue, order_count,
               SUM(revenue) OVER (PARTITION BY country_region_code ORDER BY month_start ROWS UNBOUNDED PRECEDING) AS running_revenue
        FROM MonthlySales ORDER BY country_region_code, month_start;
    """, params)
    rate_distribution = execute_sql_query(f"""
        SELECT cr.FromCurrencyCode AS from_currency_code, cr.ToCurrencyCode AS to_currency_code,
               COUNT(*) AS order_count, SUM(h.SubTotal) AS recorded_revenue, AVG(cr.AverageRate) AS average_rate,
               MIN(cr.AverageRate) AS min_rate, MAX(cr.AverageRate) AS max_rate, AVG(cr.EndOfDayRate) AS average_end_of_day_rate
        FROM Sales.SalesOrderHeader AS h
        JOIN Sales.SalesTerritory AS t ON t.TerritoryID = h.TerritoryID
        JOIN Sales.CurrencyRate AS cr ON cr.CurrencyRateID = h.CurrencyRateID
        {where_sql}
        GROUP BY cr.FromCurrencyCode, cr.ToCurrencyCode ORDER BY recorded_revenue DESC;
    """, params)
    return {"filters": {"country_region_code": country_region_code, "start_date": start_date, "end_date": end_date},
            "territory_sales": territory_sales, "local_currency_mappings": currencies,
            "monthly_sales": monthly_sales, "currency_rate_distribution": rate_distribution,
            "conversion_note": "Recorded sales amounts are not converted; CurrencyRate direction is returned separately."}
