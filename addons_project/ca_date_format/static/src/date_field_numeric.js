/** @odoo-module **/
/**
 * Force numeric date format DD/MM/YYYY on all date/datetime fields
 * across all views (form, list, kanban, pivot...).
 *
 * Can be disabled per field via: options="{'numeric': False}"
 */

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { dateField, dateTimeField, dateRangeField } from "@web/views/fields/datetime/datetime_field";
import { listDateField, listDateRangeField, listDateTimeField } from "@web/views/fields/datetime/list_datetime_field";
import { formatDate, formatDateTime } from "@web/views/fields/formatters";
import { RemainingDaysField } from "@web/views/fields/remaining_days/remaining_days_field";
import { exprToBoolean } from "@web/core/utils/strings";

/**
 * Wraps a field descriptor's extractProps to default numeric=true.
 * @param {object} fieldDescriptor - original dateField / dateTimeField / dateRangeField
 */
function withNumeric(fieldDescriptor) {
    return function extractProps(info, dynamicInfo) {
        return {
            ...fieldDescriptor.extractProps(info, dynamicInfo),
            numeric: exprToBoolean(info.options?.numeric ?? true),
        };
    };
}

// Date/datetime field components (form, kanban, editable list) ---
// extractProps builds the OWL component props; we default numeric=true here.

registry.category("fields").add(
    "date",
    { ...dateField, extractProps: withNumeric(dateField) },
    { force: true }
);

registry.category("fields").add(
    "datetime",
    { ...dateTimeField, extractProps: withNumeric(dateTimeField) },
    { force: true }
);

registry.category("fields").add(
    "daterange",
    { ...dateRangeField, extractProps: withNumeric(dateRangeField) },
    { force: true }
);

registry.category("fields").add(
    "list.date",
    { ...listDateField, extractProps: withNumeric(listDateField) },
    { force: true }
);

registry.category("fields").add(
    "list.datetime",
    { ...listDateTimeField, extractProps: withNumeric(listDateTimeField) },
    { force: true }
);

registry.category("fields").add(
    "list.daterange",
    { ...listDateRangeField, extractProps: withNumeric(listDateRangeField) },
    { force: true }
);

// Formatters (readonly list, pivot, export, group-by) ---
// In readonly list view, Odoo calls extractOptions then passes the result to the
// formatter function — we mutate the reference already stored in the registry.

const _origDateExtractOptions = formatDate.extractOptions;
formatDate.extractOptions = (info) => ({
    ..._origDateExtractOptions(info),
    numeric: exprToBoolean(info.options?.numeric ?? true),
});

const _origDateTimeExtractOptions = formatDateTime.extractOptions;
formatDateTime.extractOptions = (info) => ({
    ..._origDateTimeExtractOptions(info),
    numeric: exprToBoolean(info.options?.numeric ?? true),
});

// RemainingDaysField (remaining_days widget: stock, MRP, purchase) ---
// This widget reads formattedValue by calling formatDate() without options,
// bypassing both patches above — so we patch it directly.

patch(RemainingDaysField.prototype, {
    get formattedValue() {
        const { record, name } = this.props;
        return formatDate(record.data[name], { numeric: true });
    },
});
