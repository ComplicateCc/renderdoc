/******************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 Baldur Karlsson
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 ******************************************************************************/

#include "TAPerformanceViewer.h"
#include <QApplication>
#include <QFile>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QMap>
#include <QTextStream>
#include <QToolButton>
#include <QVBoxLayout>
#include "Code/QRDUtils.h"
#include "Code/Resources.h"
#include "Widgets/Extended/RDTreeView.h"
#include "Windows/Dialogs/PerformanceCounterSelection.h"

static const int EIDRole = Qt::UserRole + 1;
static const int SortDataRole = Qt::UserRole + 2;

enum class TAColumn
{
  Event = 0,
  Action,
  Type,
  Draws,
  Dispatches,
  Vertices,
  Triangles,
  Children,
  Count,
};

static const int BaseColumnCount = (int)TAColumn::Count;

struct TAPerformanceNode
{
  ~TAPerformanceNode()
  {
    qDeleteAll(children);
  }

  TAPerformanceNode *parent = NULL;
  QList<TAPerformanceNode *> children;
  uint32_t eventId = 0;
  QString name;
  QString type;
  uint32_t localDraws = 0;
  uint32_t localDispatches = 0;
  uint64_t localVertices = 0;
  uint64_t localTriangles = 0;
  uint32_t draws = 0;
  uint32_t dispatches = 0;
  uint64_t vertices = 0;
  uint64_t triangles = 0;
};

static QString ActionTypeName(const ActionDescription &action)
{
  if(action.flags & ActionFlags::Drawcall)
    return QApplication::translate("TAPerformanceViewer", "Draw");
  if(action.flags & ActionFlags::MeshDispatch)
    return QApplication::translate("TAPerformanceViewer", "Mesh Dispatch");
  if(action.flags & ActionFlags::Dispatch)
    return QApplication::translate("TAPerformanceViewer", "Dispatch");
  if(action.flags & (ActionFlags::SetMarker | ActionFlags::PushMarker | ActionFlags::PopMarker))
    return QApplication::translate("TAPerformanceViewer", "Marker");
  if(action.flags & ActionFlags::Copy)
    return QApplication::translate("TAPerformanceViewer", "Copy");
  if(action.flags & ActionFlags::Resolve)
    return QApplication::translate("TAPerformanceViewer", "Resolve");
  if(action.flags & ActionFlags::Clear)
    return QApplication::translate("TAPerformanceViewer", "Clear");
  return QApplication::translate("TAPerformanceViewer", "Action");
}

class TAPerformanceModel : public QAbstractItemModel
{
public:
  TAPerformanceModel(ICaptureContext &ctx, QObject *parent) : QAbstractItemModel(parent), m_Ctx(ctx)
  {
    m_Root = new TAPerformanceNode;
  }

  ~TAPerformanceModel()
  {
    delete m_Root;
  }

  void refresh(const rdcarray<CounterDescription> &counterDescriptions = {},
               const rdcarray<CounterResult> &counterResults = {})
  {
    beginResetModel();
    delete m_Root;
    m_Root = new TAPerformanceNode;
    m_CounterDescriptions = counterDescriptions;
    m_CounterData.clear();

    QMap<GPUCounter, int> counterToCol;
    for(int i = 0; i < m_CounterDescriptions.count(); i++)
      counterToCol[m_CounterDescriptions[i].counter] = i;

    for(const CounterResult &result : counterResults)
    {
      if(!counterToCol.contains(result.counter))
        continue;
      m_CounterData[result.eventId].resize(m_CounterDescriptions.count());
      m_CounterData[result.eventId][counterToCol[result.counter]] = result;
    }

    for(const ActionDescription &action : m_Ctx.CurRootActions())
      m_Root->children.push_back(BuildNode(action, m_Root));

    endResetModel();
  }

  QModelIndex index(int row, int column, const QModelIndex &parent = QModelIndex()) const override
  {
    TAPerformanceNode *parentNode = NodeForIndex(parent);
    if(row < 0 || row >= parentNode->children.count() || column < 0 || column >= columnCount())
      return QModelIndex();

    return createIndex(row, column, parentNode->children[row]);
  }

  QModelIndex parent(const QModelIndex &index) const override
  {
    if(!index.isValid())
      return QModelIndex();

    TAPerformanceNode *node = NodeForIndex(index);
    TAPerformanceNode *parentNode = node ? node->parent : NULL;
    if(parentNode == NULL || parentNode == m_Root)
      return QModelIndex();

    TAPerformanceNode *grandParent = parentNode->parent ? parentNode->parent : m_Root;
    int row = grandParent->children.indexOf(parentNode);
    return row >= 0 ? createIndex(row, 0, parentNode) : QModelIndex();
  }

  int rowCount(const QModelIndex &parent = QModelIndex()) const override
  {
    return NodeForIndex(parent)->children.count();
  }

  int columnCount(const QModelIndex &parent = QModelIndex()) const override
  {
    return BaseColumnCount + m_CounterDescriptions.count();
  }

  QVariant headerData(int section, Qt::Orientation orientation, int role) const override
  {
    if(orientation != Qt::Horizontal || role != Qt::DisplayRole)
      return QVariant();

    if(section >= BaseColumnCount)
    {
      const CounterDescription &desc = m_CounterDescriptions[section - BaseColumnCount];
      QString unit;
      switch(desc.unit)
      {
        case CounterUnit::Bytes: unit = lit("bytes"); break;
        case CounterUnit::Cycles: unit = lit("cycles"); break;
        case CounterUnit::Percentage: unit = lit("%"); break;
        case CounterUnit::Seconds: unit = UnitSuffix(m_Ctx.Config().EventBrowser_TimeUnit); break;
        case CounterUnit::Hertz: unit = lit("Hz"); break;
        case CounterUnit::Volt: unit = lit("V"); break;
        case CounterUnit::Celsius: unit = lit("°C"); break;
        case CounterUnit::Absolute:
        case CounterUnit::Ratio: break;
      }

      return unit.isEmpty() ? desc.name : QFormatStr("%1 (%2)").arg(desc.name, unit);
    }

    switch((TAColumn)section)
    {
      case TAColumn::Event: return tr("EID");
      case TAColumn::Action: return tr("Action");
      case TAColumn::Type: return tr("Type");
      case TAColumn::Draws: return tr("Draws");
      case TAColumn::Dispatches: return tr("Dispatches");
      case TAColumn::Vertices: return tr("Vertices/Indices");
      case TAColumn::Triangles: return tr("Triangles (est.)");
      case TAColumn::Children: return tr("Children");
      default: break;
    }

    return QVariant();
  }

  QVariant data(const QModelIndex &index, int role = Qt::DisplayRole) const override
  {
    if(!index.isValid())
      return QVariant();

    TAPerformanceNode *node = NodeForIndex(index);
    int rawCol = index.column();
    TAColumn col = (TAColumn)rawCol;

    if(role == EIDRole)
      return node->eventId;

    if(role == Qt::TextAlignmentRole)
    {
      if(rawCol == (int)TAColumn::Action || rawCol == (int)TAColumn::Type)
        return QVariant(Qt::AlignLeft | Qt::AlignVCenter);
      return QVariant(Qt::AlignRight | Qt::AlignVCenter);
    }

    if(rawCol >= BaseColumnCount)
      return CounterData(node, rawCol - BaseColumnCount, role);

    if(role == SortDataRole)
    {
      switch(col)
      {
        case TAColumn::Event: return (qulonglong)node->eventId;
        case TAColumn::Action: return node->name;
        case TAColumn::Type: return node->type;
        case TAColumn::Draws: return (qulonglong)node->draws;
        case TAColumn::Dispatches: return (qulonglong)node->dispatches;
        case TAColumn::Vertices: return (qulonglong)node->vertices;
        case TAColumn::Triangles: return (qulonglong)node->triangles;
        case TAColumn::Children: return node->children.count();
        default: break;
      }
    }

    if(role == Qt::DisplayRole)
    {
      switch(col)
      {
        case TAColumn::Event: return node->eventId ? QVariant((qulonglong)node->eventId) : QVariant();
        case TAColumn::Action: return node->name;
        case TAColumn::Type: return node->type;
        case TAColumn::Draws: return node->draws ? QVariant((qulonglong)node->draws) : QVariant();
        case TAColumn::Dispatches:
          return node->dispatches ? QVariant((qulonglong)node->dispatches) : QVariant();
        case TAColumn::Vertices:
          return node->vertices ? QVariant((qulonglong)node->vertices) : QVariant();
        case TAColumn::Triangles:
          return node->triangles ? QVariant((qulonglong)node->triangles) : QVariant();
        case TAColumn::Children:
          return node->children.count() ? QVariant(node->children.count()) : QVariant();
        default: break;
      }
    }

    return QVariant();
  }

  Qt::ItemFlags flags(const QModelIndex &index) const override
  {
    if(!index.isValid())
      return 0;
    return QAbstractItemModel::flags(index);
  }

private:
  QVariant CounterData(TAPerformanceNode *node, int counterIdx, int role) const
  {
    if(counterIdx < 0 || counterIdx >= m_CounterDescriptions.count())
      return QVariant();

    const CounterDescription &desc = m_CounterDescriptions[counterIdx];

    bool isUInt = desc.resultType == CompType::UInt;

    bool hasValue = false;
    double value = CounterValue(node, counterIdx, hasValue);
    if(!hasValue)
      return QVariant();

    uint64_t uvalue = (uint64_t)value;

    if(role == SortDataRole)
      return isUInt ? QVariant((qulonglong)uvalue) : QVariant(value);

    if(role != Qt::DisplayRole)
      return QVariant();

    if(isUInt)
      return (qulonglong)uvalue;

    if(desc.unit == CounterUnit::Seconds)
    {
      TimeUnit timeUnit = m_Ctx.Config().EventBrowser_TimeUnit;
      if(timeUnit == TimeUnit::Milliseconds)
        value *= 1000.0;
      else if(timeUnit == TimeUnit::Microseconds)
        value *= 1000000.0;
      else if(timeUnit == TimeUnit::Nanoseconds)
        value *= 1000000000.0;
    }

    return Formatter::Format(value);
  }

  double CounterValue(TAPerformanceNode *node, int counterIdx, bool &hasValue) const
  {
    double value = 0.0;

    if(m_CounterData.contains(node->eventId) && counterIdx < m_CounterData[node->eventId].count())
    {
      const CounterResult &result = m_CounterData[node->eventId][counterIdx];
      const CounterDescription &desc = m_CounterDescriptions[counterIdx];

      hasValue = true;
      if(desc.resultType == CompType::UInt)
        return (double)(desc.resultByteWidth == 4 ? result.value.u32 : result.value.u64);
      return desc.resultByteWidth == 4 ? (double)result.value.f : result.value.d;
    }

    for(TAPerformanceNode *child : node->children)
    {
      bool childHasValue = false;
      value += CounterValue(child, counterIdx, childHasValue);
      hasValue = hasValue || childHasValue;
    }

    return value;
  }

  TAPerformanceNode *NodeForIndex(const QModelIndex &index) const
  {
    if(index.isValid())
      return (TAPerformanceNode *)index.internalPointer();
    return m_Root;
  }

  TAPerformanceNode *BuildNode(const ActionDescription &action, TAPerformanceNode *parent)
  {
    TAPerformanceNode *node = new TAPerformanceNode;
    node->parent = parent;
    node->eventId = action.eventId;
    node->name = action.GetName(m_Ctx.GetStructuredFile());
    if(node->name.isEmpty())
      node->name = QFormatStr("Event %1").arg(action.eventId);
    node->type = ActionTypeName(action);

    if(action.flags & (ActionFlags::Drawcall | ActionFlags::MeshDispatch))
    {
      node->localDraws = 1;
      node->localVertices = (uint64_t)action.numIndices * qMax(1U, action.numInstances);
      node->localTriangles = node->localVertices / 3;
    }
    if(action.flags & ActionFlags::Dispatch)
      node->localDispatches = 1;

    node->draws = node->localDraws;
    node->dispatches = node->localDispatches;
    node->vertices = node->localVertices;
    node->triangles = node->localTriangles;

    for(const ActionDescription &childAction : action.children)
    {
      TAPerformanceNode *child = BuildNode(childAction, node);
      node->children.push_back(child);
      node->draws += child->draws;
      node->dispatches += child->dispatches;
      node->vertices += child->vertices;
      node->triangles += child->triangles;
    }

    return node;
  }

  ICaptureContext &m_Ctx;
  TAPerformanceNode *m_Root = NULL;
  rdcarray<CounterDescription> m_CounterDescriptions;
  QMap<uint32_t, rdcarray<CounterResult>> m_CounterData;
};

class TAPerformanceFilterModel : public QSortFilterProxyModel
{
public:
  TAPerformanceFilterModel(ICaptureContext &ctx, QObject *parent) : QSortFilterProxyModel(parent), m_Ctx(ctx) {}

  void refresh(bool sync)
  {
    m_Sync = sync;
    invalidateFilter();
  }

  void setHideEmptyDraws(bool hide)
  {
    m_HideEmptyDraws = hide;
    invalidateFilter();
  }

protected:
  bool filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const override
  {
    QModelIndex idx = sourceModel()->index(sourceRow, 0, sourceParent);

    if(m_HideEmptyDraws && sourceModel()->index(sourceRow, (int)TAColumn::Draws, sourceParent)
                               .data(SortDataRole)
                               .toULongLong() == 0)
      return false;

    if(!m_Sync)
      return true;

    uint32_t eid = idx.data(EIDRole).toUInt();
    if(eid == 0)
      return true;

    if(m_Ctx.GetEventBrowser()->IsAPIEventVisible(eid))
      return true;

    for(int r = 0; r < sourceModel()->rowCount(idx); r++)
      if(filterAcceptsRow(r, idx))
        return true;

    return false;
  }

  bool lessThan(const QModelIndex &left, const QModelIndex &right) const override
  {
    return sourceModel()->data(left, SortDataRole) < sourceModel()->data(right, SortDataRole);
  }

private:
  ICaptureContext &m_Ctx;
  bool m_Sync = false;
  bool m_HideEmptyDraws = false;
};

TAPerformanceViewer::TAPerformanceViewer(ICaptureContext &ctx, QWidget *parent)
    : QFrame(parent), m_Ctx(ctx)
{
  setWindowTitle(tr("TA Performance Viewer"));

  QVBoxLayout *layout = new QVBoxLayout(this);
  layout->setSpacing(0);
  layout->setContentsMargins(3, 3, 3, 3);

  QHBoxLayout *toolbar = new QHBoxLayout();
  toolbar->setSpacing(2);
  toolbar->setContentsMargins(0, 0, 0, 0);
  layout->addLayout(toolbar);

  m_Refresh = new QToolButton(this);
  m_Refresh->setText(tr("Refresh"));
  m_Refresh->setIcon(Icons::arrow_refresh());
  m_Refresh->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
  m_Refresh->setAutoRaise(true);
  toolbar->addWidget(m_Refresh);

  m_CaptureCounters = new QToolButton(this);
  m_CaptureCounters->setText(tr("Capture counters"));
  m_CaptureCounters->setIcon(Icons::time());
  m_CaptureCounters->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
  m_CaptureCounters->setAutoRaise(true);
  toolbar->addWidget(m_CaptureCounters);

  m_Sync = new QToolButton(this);
  m_Sync->setText(tr("Sync with Event Browser"));
  m_Sync->setIcon(Icons::arrow_join());
  m_Sync->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
  m_Sync->setCheckable(true);
  m_Sync->setAutoRaise(true);
  toolbar->addWidget(m_Sync);

  m_HideEmptyDraws = new QToolButton(this);
  m_HideEmptyDraws->setText(tr("Hide no-draw nodes"));
  m_HideEmptyDraws->setIcon(Icons::filter());
  m_HideEmptyDraws->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
  m_HideEmptyDraws->setCheckable(true);
  m_HideEmptyDraws->setAutoRaise(true);
  toolbar->addWidget(m_HideEmptyDraws);

  m_Expand = new QToolButton(this);
  m_Expand->setText(tr("Expand All"));
  m_Expand->setIcon(Icons::arrow_out());
  m_Expand->setAutoRaise(true);
  toolbar->addWidget(m_Expand);

  m_Collapse = new QToolButton(this);
  m_Collapse->setText(tr("Collapse All"));
  m_Collapse->setIcon(Icons::arrow_in());
  m_Collapse->setAutoRaise(true);
  toolbar->addWidget(m_Collapse);

  m_SaveCSV = new QToolButton(this);
  m_SaveCSV->setIcon(Icons::save());
  m_SaveCSV->setToolTip(tr("Export to CSV"));
  m_SaveCSV->setAutoRaise(true);
  toolbar->addWidget(m_SaveCSV);
  toolbar->addStretch(1);

  m_Tree = new RDTreeView(this);
  m_Tree->setSelectionMode(QAbstractItemView::ExtendedSelection);
  m_Tree->setSelectionBehavior(QAbstractItemView::SelectRows);
  m_Tree->setSortingEnabled(true);
  m_Tree->setFont(Formatter::PreferredFont());
  m_Tree->header()->setSectionsMovable(true);
  layout->addWidget(m_Tree);

  m_Model = new TAPerformanceModel(m_Ctx, this);
  m_Filter = new TAPerformanceFilterModel(m_Ctx, this);
  m_Filter->setSourceModel(m_Model);
  m_Tree->setModel(m_Filter);
  m_Tree->sortByColumn((int)TAColumn::Event, Qt::AscendingOrder);

  QObject::connect(m_Refresh, &QToolButton::clicked, [this]() { Refresh(); });
  QObject::connect(m_CaptureCounters, &QToolButton::clicked, [this]() { CaptureCounters(); });
  QObject::connect(m_Sync, &QToolButton::toggled, [this](bool checked) {
    m_Filter->refresh(checked);
    SyncToEvent(m_Ctx.CurEvent());
  });
  QObject::connect(m_HideEmptyDraws, &QToolButton::toggled,
                   [this](bool checked) { m_Filter->setHideEmptyDraws(checked); });
  QObject::connect(m_Expand, &QToolButton::clicked, m_Tree, &QTreeView::expandAll);
  QObject::connect(m_Collapse, &QToolButton::clicked, m_Tree, &QTreeView::collapseAll);
  QObject::connect(m_SaveCSV, &QToolButton::clicked, [this]() { ExportCSV(); });
  QObject::connect(m_Tree, &QTreeView::doubleClicked, [this](const QModelIndex &index) {
    uint32_t eid = index.data(EIDRole).toUInt();
    if(eid)
      m_Ctx.SetEventID({}, eid, eid);
  });

  m_Ctx.AddCaptureViewer(this);
  Refresh();
}

TAPerformanceViewer::~TAPerformanceViewer()
{
  m_Ctx.BuiltinWindowClosed(this);
  m_Ctx.RemoveCaptureViewer(this);
}

void TAPerformanceViewer::Refresh()
{
  m_Refresh->setEnabled(m_Ctx.IsCaptureLoaded());
  m_CaptureCounters->setEnabled(m_Ctx.IsCaptureLoaded());
  m_SaveCSV->setEnabled(m_Ctx.IsCaptureLoaded());
  m_Model->refresh(m_CounterDescriptions, m_CounterResults);
  m_Filter->refresh(m_Sync->isChecked());
  m_Filter->setHideEmptyDraws(m_HideEmptyDraws->isChecked());
  m_Tree->resizeColumnToContents((int)TAColumn::Action);
}

void TAPerformanceViewer::CaptureCounters()
{
  if(!m_Ctx.IsCaptureLoaded())
    return;

  PerformanceCounterSelection pcs(m_Ctx, m_SelectedCounters, this);
  if(RDDialog::show(&pcs) != QDialog::Accepted)
    return;
  m_SelectedCounters = pcs.GetSelectedCounters();

  bool done = false;
  m_Ctx.Replay().AsyncInvoke([this, &done](IReplayController *controller) {
    rdcarray<GPUCounter> counters;
    counters.resize(m_SelectedCounters.size());

    rdcarray<CounterDescription> descriptions;
    for(int i = 0; i < m_SelectedCounters.size(); i++)
    {
      counters[i] = (GPUCounter)m_SelectedCounters[i];
      descriptions.push_back(controller->DescribeCounter(counters[i]));
    }

    rdcarray<CounterResult> results = controller->FetchCounters(counters);

    GUIInvoke::call(this, [this, descriptions, results]() {
      m_CounterDescriptions = descriptions;
      m_CounterResults = results;
      Refresh();
      for(int c = 0; c < m_Tree->model()->columnCount(); c++)
        m_Tree->resizeColumnToContents(c);
    });

    done = true;
  });

  ShowProgressDialog(this, tr("Capturing counters"), [&done]() { return done; });
}

void TAPerformanceViewer::OnCaptureLoaded()
{
  Refresh();
}

void TAPerformanceViewer::OnCaptureClosed()
{
  m_CounterDescriptions.clear();
  m_CounterResults.clear();
  Refresh();
}

void TAPerformanceViewer::OnEventChanged(uint32_t eventId)
{
  if(m_Sync->isChecked())
  {
    m_Filter->refresh(true);
    SyncToEvent(eventId);
  }
}

void TAPerformanceViewer::SyncToEvent(uint32_t eventId)
{
  if(!eventId)
    return;

  QList<QModelIndex> stack;
  for(int r = 0; r < m_Filter->rowCount(); r++)
    stack.push_back(m_Filter->index(r, 0));

  while(!stack.isEmpty())
  {
    QModelIndex idx = stack.takeLast();
    if(idx.data(EIDRole).toUInt() == eventId)
    {
      m_Tree->setCurrentIndex(idx);
      m_Tree->scrollTo(idx);
      return;
    }

    for(int r = 0; r < m_Filter->rowCount(idx); r++)
      stack.push_back(m_Filter->index(r, 0, idx));
  }
}

static void ExportNodeCSV(QTextStream &ts, QAbstractItemModel *model, const QModelIndex &parent, int depth)
{
  for(int row = 0; row < model->rowCount(parent); row++)
  {
    QModelIndex first = model->index(row, 0, parent);
    for(int col = 0; col < model->columnCount(parent); col++)
    {
      QString text = model->index(row, col, parent).data().toString();
      if(col == (int)TAColumn::Action)
        text = QString(depth * 2, QLatin1Char(' ')) + text;
      ts << text;
      ts << (col + 1 == model->columnCount(parent) ? lit("\n") : lit(","));
    }
    ExportNodeCSV(ts, model, first, depth + 1);
  }
}

void TAPerformanceViewer::ExportCSV()
{
  QString filename = RDDialog::getSaveFileName(this, tr("Export TA performance tree as CSV"), QString(),
                                               tr("CSV Files (*.csv)"));
  if(filename.isEmpty())
    return;

  QFile f(filename, this);
  if(!f.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text))
  {
    RDDialog::critical(this, tr("Error exporting TA performance tree"),
                       tr("Couldn't open path %1 for write.\n%2").arg(filename).arg(f.errorString()));
    return;
  }

  QTextStream ts(&f);
  QAbstractItemModel *model = m_Tree->model();
  for(int col = 0; col < model->columnCount(); col++)
  {
    ts << model->headerData(col, Qt::Horizontal).toString();
    ts << (col + 1 == model->columnCount() ? lit("\n") : lit(","));
  }
  ExportNodeCSV(ts, model, QModelIndex(), 0);
}
